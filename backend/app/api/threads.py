"""
KAM v2 线程 API
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.conversation_router import ConversationRouter
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


@router.post("/threads/{thread_id}/messages")
async def create_message(thread_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    thread_service = ThreadService(db)
    router = ConversationRouter(db)

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

    routed = router.route(
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

    return {
        "message": message.to_dict(include_runs=True),
        "reply": reply.to_dict(include_runs=True) if reply else None,
        "runs": routed.get("runs") or [],
        "preferences": routed.get("preferences") or [],
        "routerMode": routed.get("routerMode") or "heuristic",
    }
