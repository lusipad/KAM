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
        "routerMode": routed.get("routerMode") or "heuristic",
        "compareId": routed.get("compareId"),
    }
    if project is not None:
        payload["project"] = project.to_dict(include_relations=True, include_threads=True)
    if thread is not None:
        payload["thread"] = thread.to_dict(include_relations=True, include_runs=True)
    return payload


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
        last_payload: str | None = None

        while True:
            if await request.is_disconnected():
                break

            stream_db = SessionLocal()
            try:
                stream_service = ThreadService(stream_db)
                current_thread = stream_service.get_thread(thread_id)
                if not current_thread:
                    break

                has_active_runs = any(run.status in ACTIVE_RUN_STATUSES for run in (current_thread.runs or []))
                payload = {
                    "thread": current_thread.to_dict(include_relations=True, include_runs=True),
                    "hasActiveRuns": has_active_runs,
                }
                serialized = json.dumps(payload, ensure_ascii=False)
                if serialized != last_payload:
                    last_payload = serialized
                    yield f"data: {serialized}\n\n"
                else:
                    yield ": keep-alive\n\n"

                if not has_active_runs:
                    break
            finally:
                stream_db.close()

            await asyncio.sleep(1)

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

    routed = conversation_router.route(
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
async def create_message(thread_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    thread_service = ThreadService(db)
    conversation_router = ConversationRouter(db)

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

    routed = conversation_router.route(
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

    return _build_message_response(
        thread_service=thread_service,
        thread_id=thread_id,
        message=message,
        reply=reply,
        routed=routed,
    )
