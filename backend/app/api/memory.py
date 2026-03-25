"""
KAM v2 记忆 API
"""
from __future__ import annotations

from typing import Optional

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
    embedding: Optional[list[float]] = None
    sourceThreadId: Optional[str] = None


class PreferenceUpdate(BaseModel):
    value: str = Field(..., min_length=1)
    embedding: Optional[list[float]] = None
    sourceThreadId: Optional[str] = None


class DecisionCreate(BaseModel):
    projectId: Optional[str] = None
    question: str = Field(..., min_length=1)
    decision: str = Field(..., min_length=1)
    reasoning: str = ""
    embedding: Optional[list[float]] = None
    sourceThreadId: Optional[str] = None


class DecisionUpdate(BaseModel):
    question: str = Field(..., min_length=1)
    decision: str = Field(..., min_length=1)
    reasoning: str = ""
    embedding: Optional[list[float]] = None
    sourceThreadId: Optional[str] = None


class LearningCreate(BaseModel):
    projectId: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    embedding: Optional[list[float]] = None
    sourceThreadId: Optional[str] = None


class LearningUpdate(BaseModel):
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
    return service.create_preference(data.model_dump(exclude_none=True)).to_dict()


@router.put("/memory/preferences/{preference_id}")
async def update_preference(preference_id: str, data: PreferenceUpdate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    preference = service.update_preference(preference_id, data.model_dump(exclude_none=True))
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
    return service.create_decision(data.model_dump(exclude_none=True)).to_dict()


@router.put("/memory/decisions/{decision_id}")
async def update_decision(decision_id: str, data: DecisionUpdate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    decision = service.update_decision(decision_id, data.model_dump(exclude_none=True))
    if not decision:
        raise HTTPException(status_code=404, detail="决策不存在")
    return decision.to_dict()


@router.get("/memory/learnings")
async def list_learnings(
    project_id: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = MemoryService(db)
    return {"learnings": [item.to_dict() for item in service.list_learnings(project_id=project_id, query=query)]}


@router.post("/memory/learnings")
async def create_learning(data: LearningCreate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    return service.create_learning(data.model_dump(exclude_none=True)).to_dict()


@router.put("/memory/learnings/{learning_id}")
async def update_learning(learning_id: str, data: LearningUpdate, db: Session = Depends(get_db)):
    service = MemoryService(db)
    learning = service.update_learning(learning_id, data.model_dump(exclude_none=True))
    if not learning:
        raise HTTPException(status_code=404, detail="learning 不存在")
    return learning.to_dict()


@router.get("/memory/search")
async def search_memory(
    query: str = Query(default=""),
    project_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = MemoryService(db)
    return service.search(query=query, project_id=project_id)
