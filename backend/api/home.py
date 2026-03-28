from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import get_db
from events import event_bus
from models import Run, WatcherEvent


router = APIRouter(prefix="/home", tags=["home"])


def _greeting_for_now() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "上午好"
    if hour < 18:
        return "下午好"
    return "晚上好"


def _run_item(run: Run) -> dict[str, Any]:
    return {"kind": "run", **run.to_dict()}


def _watcher_event_item(event: WatcherEvent) -> dict[str, Any]:
    return {"kind": "watcher_event", **event.to_dict()}


def _attention_priority(item: dict[str, Any]) -> tuple[int, float]:
    if item["kind"] == "run":
        if item["status"] == "failed":
            return (0, -datetime.fromisoformat(item["createdAt"]).timestamp())
        if item["status"] == "passed":
            return (2, -datetime.fromisoformat(item["createdAt"]).timestamp())
        return (4, -datetime.fromisoformat(item["createdAt"]).timestamp())

    event_type = str(item.get("eventType", "")).lower()
    title = str(item.get("title", "")).lower()
    urgent = any(token in event_type or token in title for token in ("fail", "error", "blocked", "review"))
    return (1 if urgent else 2, -datetime.fromisoformat(item["createdAt"]).timestamp())


@router.get("/feed")
async def get_feed(db: AsyncSession = Depends(get_db)):
    attention_runs_stmt = (
        select(Run)
        .where(or_(and_(Run.status == "passed", Run.adopted_at.is_(None)), Run.status == "failed"))
        .order_by(Run.created_at.desc())
        .limit(10)
    )
    attention_runs_result = await db.execute(attention_runs_stmt)
    attention_events_result = await db.execute(
        select(WatcherEvent)
        .options(selectinload(WatcherEvent.watcher))
        .where(WatcherEvent.status == "pending")
        .order_by(WatcherEvent.created_at.desc())
        .limit(10)
    )
    running_result = await db.execute(select(Run).where(Run.status == "running").order_by(Run.created_at.desc()))
    recent_result = await db.execute(
        select(Run)
        .where(or_(and_(Run.status == "passed", Run.adopted_at.is_not(None)), Run.status == "cancelled"))
        .order_by(Run.created_at.desc())
        .limit(5)
    )

    attention_runs = list(attention_runs_result.scalars())
    attention_events = list(attention_events_result.scalars())
    running = list(running_result.scalars())
    recent = list(recent_result.scalars())
    pending_adoptions = sum(1 for item in attention_runs if item.status == "passed")
    needs_attention = [_run_item(run) for run in attention_runs] + [_watcher_event_item(event) for event in attention_events]
    needs_attention.sort(key=_attention_priority)

    return {
        "greeting": _greeting_for_now(),
        "summary": f"后台有 {len(running)} 个任务执行中，{len(attention_events)} 条监控提醒，{pending_adoptions} 个结果等待采纳。",
        "needsAttention": needs_attention,
        "running": [_run_item(run) for run in running],
        "recent": [_run_item(run) for run in recent],
    }


@router.get("/events")
async def stream_home_events(request: Request):
    queue = await event_bus.subscribe("home")

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                    yield {"event": event.get("type", "message"), "data": json.dumps(event, ensure_ascii=False)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await event_bus.unsubscribe("home", queue)

    return EventSourceResponse(generate())
