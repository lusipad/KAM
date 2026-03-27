from __future__ import annotations

import asyncio
import json
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


def _run_item(run: Run) -> dict[str, Any]:
    return {"kind": "run", **run.to_dict()}


def _watcher_event_item(event: WatcherEvent) -> dict[str, Any]:
    return {"kind": "watcher_event", **event.to_dict()}


@router.get("/feed")
async def get_feed(db: AsyncSession = Depends(get_db)):
    attention_runs_result = await db.execute(
        select(Run)
        .where(or_(and_(Run.status == "passed", Run.adopted_at.is_(None)), Run.status == "failed"))
        .order_by(Run.created_at.desc())
        .limit(10)
    )
    attention_events_result = await db.execute(
        select(WatcherEvent)
        .options(selectinload(WatcherEvent.watcher))
        .where(WatcherEvent.status == "pending")
        .order_by(WatcherEvent.created_at.desc())
        .limit(10)
    )
    running_result = await db.execute(select(Run).where(Run.status == "running").order_by(Run.created_at.desc()))
    recent_result = await db.execute(
        select(Run).where(Run.status.in_(["passed", "failed"])).order_by(Run.created_at.desc()).limit(5)
    )

    attention_runs = list(attention_runs_result.scalars())
    attention_events = list(attention_events_result.scalars())
    running = list(running_result.scalars())
    recent = list(recent_result.scalars())

    return {
        "greeting": "Good afternoon",
        "summary": f"{len(running)} tasks running, {len(attention_events)} watcher alerts, {sum(1 for item in attention_runs if item.status == 'passed')} tasks waiting to adopt.",
        "needsAttention": [_run_item(run) for run in attention_runs] + [_watcher_event_item(event) for event in attention_events],
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
                    yield {"event": event.get("type", "message"), "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await event_bus.unsubscribe("home", queue)

    return EventSourceResponse(generate())
