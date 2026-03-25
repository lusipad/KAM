"""
自治会话 API
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.autonomy_service import AutonomyService

router = APIRouter(tags=["autonomy"])


class AutonomyCheckInput(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    command: str = Field(..., min_length=1)


class AutonomySessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    objective: str = ""
    repoPath: Optional[str] = None
    primaryAgentName: str = Field(default="Codex", min_length=1, max_length=100)
    primaryAgentType: str = "codex"
    primaryAgentCommand: Optional[str] = None
    maxIterations: int = Field(default=3, ge=1, le=12)
    successCriteria: str = ""
    checkCommands: list[AutonomyCheckInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/tasks/{task_id}/autonomy/sessions")
async def list_task_autonomy_sessions(task_id: str, db: Session = Depends(get_db)):
    service = AutonomyService(db)
    return {"sessions": [session.to_dict() for session in service.list_sessions(task_id)]}


@router.post("/tasks/{task_id}/autonomy/sessions")
async def create_task_autonomy_session(task_id: str, data: AutonomySessionCreate, db: Session = Depends(get_db)):
    service = AutonomyService(db)
    session = service.create_session(task_id, data.model_dump())
    if not session:
        raise HTTPException(status_code=404, detail="任务不存在")
    return session.to_dict()


@router.post("/tasks/{task_id}/autonomy/dogfood")
async def create_task_dogfood_session(task_id: str, db: Session = Depends(get_db)):
    service = AutonomyService(db)
    session = service.create_dogfood_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="任务不存在")
    return session.to_dict()


@router.get("/tasks/{task_id}/autonomy/metrics")
async def get_task_autonomy_metrics(task_id: str, db: Session = Depends(get_db)):
    service = AutonomyService(db)
    return service.get_metrics(task_id=task_id)


@router.get("/autonomy/sessions/{session_id}")
async def get_autonomy_session(session_id: str, db: Session = Depends(get_db)):
    service = AutonomyService(db)
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="自治会话不存在")
    return session.to_dict()


@router.post("/autonomy/sessions/{session_id}/start")
async def start_autonomy_session(session_id: str, db: Session = Depends(get_db)):
    service = AutonomyService(db)
    session = service.start_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="自治会话不存在")
    return session.to_dict(include_cycles=False)


@router.post("/autonomy/sessions/{session_id}/interrupt")
async def interrupt_autonomy_session(session_id: str, db: Session = Depends(get_db)):
    service = AutonomyService(db)
    session = service.interrupt_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="自治会话不存在")
    return session.to_dict(include_cycles=False)


@router.get("/autonomy/metrics")
async def get_autonomy_metrics(db: Session = Depends(get_db)):
    service = AutonomyService(db)
    return service.get_metrics()
