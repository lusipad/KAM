"""
KAM v2 记忆 API（预览）
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/v2", tags=["v2-memory"])


class PreferenceCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1)
    sourceThreadId: Optional[str] = None


class PreferenceUpdate(BaseModel):
    value: str = Field(..., min_length=1)
    sourceThreadId: Optional[str] = None


class DecisionCreate(BaseModel):
    projectId: Optional[str] = None
    question: str = Field(..., min_length=1)
    decision: str = Field(..., min_length=1)
    reasoning: str = ""
    sourceThreadId: Optional[str] = None


class LearningCreate(BaseModel):
    projectId: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    embedding: Optional[list[float]] = None
    sourceThreadId: Optional[str] = None


@router.get("/memory/preferences")
async def list_preferences(category: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    service = MemoryService(db)
    return {"preferences": [item.to_dict() for item in service.list_preferences(category=category)]}


@router.post("/memory/preferences")
async def create_preference(data: PreferenceCreate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    return service.create_preference(data.model_dump()).to_dict()


@router.put("/memory/preferences/{preference_id}")
async def update_preference(preference_id: str, data: PreferenceUpdate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    preference = service.update_preference(preference_id, data.model_dump())
    if not preference:
        raise HTTPException(status_code=404, detail="偏好不存在")
    return preference.to_dict()


@router.get("/memory/decisions")
async def list_decisions(project_id: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    service = MemoryService(db)
    return {"decisions": [item.to_dict() for item in service.list_decisions(project_id=project_id)]}


@router.post("/memory/decisions")
async def create_decision(data: DecisionCreate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    return service.create_decision(data.model_dump()).to_dict()


@router.post("/memory/learnings")
async def create_learning(data: LearningCreate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    return service.create_learning(data.model_dump()).to_dict()


@router.get("/memory/search")
async def search_memory(
    query: str = Query(default=""),
    project_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = MemoryService(db)
    return service.search(query=query, project_id=project_id)
