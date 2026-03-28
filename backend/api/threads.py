from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import get_db
from events import event_bus
from models import Message, Thread, now
from services.digest import DigestService
from services.router import ConversationRouter


router = APIRouter(prefix="/threads", tags=["threads"])


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


@router.get("")
async def list_threads(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Thread)
        .options(selectinload(Thread.project), selectinload(Thread.runs))
        .order_by(Thread.updated_at.desc())
    )
    result = await db.execute(stmt)
    return {"threads": [thread.to_summary_dict() for thread in result.scalars()]}


@router.get("/{thread_id}")
async def get_thread(thread_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Thread)
        .where(Thread.id == thread_id)
        .options(selectinload(Thread.project), selectinload(Thread.messages), selectinload(Thread.runs))
    )
    result = await db.execute(stmt)
    thread = result.scalars().first()
    if thread is None:
        raise HTTPException(status_code=404, detail="线程不存在")
    appended = await DigestService(db).append_restore_summary(thread)
    if appended:
        result = await db.execute(stmt.execution_options(populate_existing=True))
        thread = result.scalars().first()
    return thread.to_detail_dict()


@router.post("/{thread_id}/messages")
async def send_message(thread_id: str, payload: MessageCreate, request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(Thread).where(Thread.id == thread_id).options(selectinload(Thread.project))
    result = await db.execute(stmt)
    thread = result.scalars().first()
    if thread is None:
        raise HTTPException(status_code=404, detail="线程不存在")

    user_message = Message(thread_id=thread.id, role="user", content=payload.content.strip())
    db.add(user_message)
    thread.updated_at = now()
    await db.commit()
    await db.refresh(user_message)
    await event_bus.publish(f"thread:{thread.id}", {"type": "thread_updated", "threadId": thread.id})

    async def generate():
        events = await ConversationRouter(db).route_message(
            thread_id=thread.id,
            message_content=payload.content,
            project_id=thread.project_id,
        )
        for event in events:
            if await request.is_disconnected():
                break
            if event["type"] == "text_done":
                assistant_message = Message(thread_id=thread.id, role="assistant", content=event["content"])
                db.add(assistant_message)
                thread.updated_at = now()
                await db.commit()
                await event_bus.publish(f"thread:{thread.id}", {"type": "thread_updated", "threadId": thread.id})
            yield {"event": event["type"], "data": json.dumps(event, ensure_ascii=False)}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())


@router.get("/{thread_id}/events")
async def stream_events(thread_id: str, request: Request):
    queue = await event_bus.subscribe(f"thread:{thread_id}")

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
            await event_bus.unsubscribe(f"thread:{thread_id}", queue)

    return EventSourceResponse(generate())
