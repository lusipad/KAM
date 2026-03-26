"""
KAM v2 线程 API
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.db.base import SessionLocal, get_db
from app.services.conversation_router import ConversationRouter
from app.services.project_service import ProjectService
from app.services.run_engine import ACTIVE_RUN_STATUSES
from app.services.thread_service import ThreadService

router = APIRouter(prefix="/v2", tags=["v2-threads"])


class ThreadCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=200)
    status: str = "active"


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    createRun: Optional[bool] = None
    agent: Optional[str] = None
    command: Optional[str] = None
    model: Optional[str] = None
    reasoningEffort: Optional[str] = None


class BootstrapMessageCreate(MessageCreate):
    projectTitle: Optional[str] = Field(default=None, max_length=200)
    projectDescription: str = ""
    projectStatus: str = "active"
    repoPath: Optional[str] = None
    checkCommands: list[str] = Field(default_factory=list)
    projectSettings: dict[str, Any] = Field(default_factory=dict)
    threadTitle: Optional[str] = Field(default=None, max_length=200)


def _infer_title(content: str, fallback: str) -> str:
    normalized = " ".join(content.strip().split())
    if not normalized:
        return fallback
    for separator in ("。", "！", "？", ".", "!", "?", "\n"):
        if separator in normalized:
            normalized = normalized.split(separator, 1)[0].strip()
            break
    normalized = normalized.strip(" ，,；;：:")
    if not normalized:
        return fallback
    return normalized[:40]


def _build_message_response(
    *,
    thread_service: ThreadService,
    thread_id: str,
    message,
    reply,
    routed: dict[str, Any],
    project=None,
) -> dict[str, Any]:
    thread = thread_service.get_thread(thread_id)
    payload = {
        "message": message.to_dict(include_runs=True),
        "reply": reply.to_dict(include_runs=True) if reply else None,
        "runs": routed.get("runs") or [],
        "preferences": routed.get("preferences") or [],
        "decisions": routed.get("decisions") or [],
        "learnings": routed.get("learnings") or [],
        "routerMode": routed.get("routerMode") or "heuristic",
        "compareId": routed.get("compareId"),
    }
    if project is not None:
        payload["project"] = project.to_dict(include_relations=True, include_threads=True)
    if thread is not None:
        payload["thread"] = thread.to_dict(include_relations=True, include_runs=True)
    return payload


def _encode_sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk_text(content: str, chunk_size: int = 36) -> list[str]:
    text = content or ""
    if not text:
        return []
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]


def _wants_sse_response(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/event-stream" in accept.lower()


def _thread_snapshot_payload(thread_id: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        service = ThreadService(db)
        thread = service.get_thread(thread_id)
        if not thread:
            return None
        has_active_runs = any(run.status in ACTIVE_RUN_STATUSES for run in (thread.runs or []))
        return {
            "thread": thread.to_dict(include_relations=True, include_runs=True),
            "hasActiveRuns": has_active_runs,
        }
    finally:
        db.close()


async def _process_thread_message(
    *,
    thread_id: str,
    data: MessageCreate,
    thread_service: ThreadService,
    conversation_router: ConversationRouter,
) -> tuple[Any, Any, dict[str, Any]]:
    message = thread_service.create_message(
        thread_id,
        {
            "role": "user",
            "content": data.content,
            "metadata": data.metadata,
        },
    )
    if not message:
        raise HTTPException(status_code=404, detail="线程不存在")

    routed = await conversation_router.route(
        thread_id=thread_id,
        message_id=str(message.id),
        user_message=data.content,
        create_run=data.createRun,
        agent=data.agent,
        command=data.command,
        model=data.model,
        reasoning_effort=data.reasoningEffort,
        metadata=data.metadata,
    )
    reply = None
    if routed.get("reply"):
        reply = thread_service.create_message(
            thread_id,
            {
                "role": "assistant",
                "content": routed["reply"],
                "metadata": {"generatedBy": "conversation-router"},
            },
        )

    return message, reply, routed


def _message_streaming_response(*, thread_id: str, data: MessageCreate, request: Request) -> StreamingResponse:
    async def event_stream():
        stream_db = SessionLocal()
        try:
            stream_thread_service = ThreadService(stream_db)
            stream_conversation_router = ConversationRouter(stream_db)
            message = stream_thread_service.create_message(
                thread_id,
                {
                    "role": "user",
                    "content": data.content,
                    "metadata": data.metadata,
                },
            )
            if not message:
                raise HTTPException(status_code=404, detail="线程不存在")

            yield _encode_sse_event(
                "message-saved",
                {
                    "message": message.to_dict(include_runs=True),
                },
            )

            accumulated = ""
            routed: dict[str, Any] = {
                "reply": "",
                "runs": [],
                "preferences": [],
                "decisions": [],
                "learnings": [],
                "context": {},
                "routerMode": "heuristic",
                "compareId": None,
            }
            async for event in stream_conversation_router.route_async(
                thread_id=thread_id,
                message_id=str(message.id),
                user_message=data.content,
                create_run=data.createRun,
                agent=data.agent,
                command=data.command,
                model=data.model,
                reasoning_effort=data.reasoningEffort,
                metadata=data.metadata,
            ):
                if await request.is_disconnected():
                    return

                event_type = str(event.get("type") or "")
                if event_type == "text_delta":
                    delta = str(event.get("delta") or "")
                    accumulated += delta
                    yield _encode_sse_event(
                        "assistant-reply-delta",
                        {
                            "delta": delta,
                            "content": accumulated,
                        },
                    )
                    continue

                if event_type == "runs_created":
                    routed["runs"] = event.get("runs") or []
                    routed["compareId"] = event.get("compareId")
                    yield _encode_sse_event(
                        "runs-created",
                        {
                            "runs": routed["runs"],
                            "compareId": routed["compareId"],
                        },
                    )
                    continue

                if event_type == "memory_recorded":
                    kind = str(event.get("kind") or "")
                    if kind == "preference":
                        routed["preferences"].append(event["record"])
                    elif kind == "decision":
                        routed["decisions"].append(event["record"])
                    elif kind == "learning":
                        routed["learnings"].append(event["record"])
                    yield _encode_sse_event(
                        "memory-recorded",
                        {
                            "kind": kind,
                            "record": event["record"],
                        },
                    )
                    continue

                if event_type == "assistant_reply_final":
                    routed["reply"] = str(event.get("content") or "").strip()
                    continue

                if event_type == "done":
                    routed["context"] = event.get("context") or {}
                    routed["routerMode"] = event.get("routerMode") or "heuristic"
                    routed["compareId"] = event.get("compareId")

            if not routed.get("reply") and accumulated.strip():
                routed["reply"] = accumulated.strip()

            reply = None
            if routed.get("reply"):
                reply = stream_thread_service.create_message(
                    thread_id,
                    {
                        "role": "assistant",
                        "content": routed["reply"],
                        "metadata": {"generatedBy": "conversation-router"},
                    },
                )
                if reply:
                    yield _encode_sse_event(
                        "assistant-reply-complete",
                        {
                            "reply": reply.to_dict(include_runs=True),
                        },
                    )

            final_payload = _build_message_response(
                thread_service=stream_thread_service,
                thread_id=thread_id,
                message=message,
                reply=reply,
                routed=routed,
            )
            yield _encode_sse_event("result", final_payload)
            yield _encode_sse_event("done", final_payload)
        except HTTPException as error:
            yield _encode_sse_event(
                "error",
                {
                    "message": error.detail,
                    "statusCode": error.status_code,
                },
            )
        except Exception as error:
            yield _encode_sse_event(
                "error",
                {
                    "message": str(error),
                },
            )
        finally:
            stream_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/threads")
async def list_threads(
    project_id: str,
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = ThreadService(db)
    return {"threads": [thread.to_dict(include_relations=False) for thread in service.list_threads(project_id, status=status)]}


@router.post("/projects/{project_id}/threads")
async def create_thread(project_id: str, data: ThreadCreate, db: Session = Depends(get_db)):
    service = ThreadService(db)
    thread = service.create_thread(project_id, data.model_dump())
    if not thread:
        raise HTTPException(status_code=404, detail="项目不存在")
    return thread.to_dict(include_relations=True, include_runs=True)


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, db: Session = Depends(get_db)):
    service = ThreadService(db)
    await ConversationRouter(db).ensure_restore_summary(thread_id)
    thread = service.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="线程不存在")
    return thread.to_dict(include_relations=True, include_runs=True)


@router.get("/threads/{thread_id}/events")
async def stream_thread_events(thread_id: str, request: Request, db: Session = Depends(get_db)):
    service = ThreadService(db)
    thread = service.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="线程不存在")

    async def event_stream():
        subscription = await event_bus.subscribe(f"thread:{thread_id}")
        while True:
            try:
                snapshot = _thread_snapshot_payload(thread_id)
                if not snapshot:
                    break
                yield _encode_sse_event("snapshot", snapshot)
                if not snapshot.get("hasActiveRuns"):
                    return

                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        event = await asyncio.wait_for(subscription.queue.get(), timeout=30)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue

                    snapshot = _thread_snapshot_payload(thread_id)
                    if not snapshot:
                        return
                    payload = {
                        **snapshot,
                        "event": event,
                    }
                    yield _encode_sse_event(str(event.get("type") or "thread-updated"), payload)
                    if event.get("type") == "thread-done" and not snapshot.get("hasActiveRuns"):
                        return
            finally:
                await event_bus.unsubscribe(subscription)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/bootstrap/message")
async def bootstrap_message(data: BootstrapMessageCreate, db: Session = Depends(get_db)):
    project_service = ProjectService(db)
    thread_service = ThreadService(db)
    conversation_router = ConversationRouter(db)

    project = project_service.create_project(
        {
            "title": (data.projectTitle or "").strip() or _infer_title(data.content, "新项目"),
            "description": data.projectDescription,
            "status": data.projectStatus,
            "repoPath": data.repoPath,
            "checkCommands": data.checkCommands,
            "settings": data.projectSettings,
        }
    )
    thread = thread_service.create_thread(
        str(project.id),
        {
            "title": (data.threadTitle or "").strip() or "新对话",
            "status": "active",
        },
    )
    if not thread:
        raise HTTPException(status_code=500, detail="项目初始化失败")

    message = thread_service.create_message(
        str(thread.id),
        {
            "role": "user",
            "content": data.content,
            "metadata": data.metadata,
        },
    )
    if not message:
        raise HTTPException(status_code=500, detail="线程初始化失败")

    routed = await conversation_router.route(
        thread_id=str(thread.id),
        message_id=str(message.id),
        user_message=data.content,
        create_run=data.createRun,
        agent=data.agent,
        command=data.command,
        model=data.model,
        reasoning_effort=data.reasoningEffort,
        metadata=data.metadata,
    )
    reply = None
    if routed.get("reply"):
        reply = thread_service.create_message(
            str(thread.id),
            {
                "role": "assistant",
                "content": routed["reply"],
                "metadata": {"generatedBy": "conversation-router"},
            },
        )

    hydrated_project = project_service.get_project(str(project.id))
    return _build_message_response(
        thread_service=thread_service,
        thread_id=str(thread.id),
        message=message,
        reply=reply,
        routed=routed,
        project=hydrated_project,
    )


@router.post("/threads/{thread_id}/messages")
async def create_message(thread_id: str, data: MessageCreate, request: Request, db: Session = Depends(get_db)):
    thread_service = ThreadService(db)
    thread = thread_service.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="线程不存在")

    if _wants_sse_response(request):
        return _message_streaming_response(thread_id=thread_id, data=data, request=request)

    conversation_router = ConversationRouter(db)

    message, reply, routed = await _process_thread_message(
        thread_id=thread_id,
        data=data,
        thread_service=thread_service,
        conversation_router=conversation_router,
    )

    return _build_message_response(
        thread_service=thread_service,
        thread_id=thread_id,
        message=message,
        reply=reply,
        routed=routed,
    )
