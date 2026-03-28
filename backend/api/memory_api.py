from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services.memory import MemoryService


router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreate(BaseModel):
    projectId: str | None = None
    scope: str = "project"
    category: str = Field(pattern="^(preference|decision|fact|learning)$")
    content: str = Field(min_length=1)
    rationale: str | None = None


class MemoryUpdate(BaseModel):
    content: str | None = None
    rationale: str | None = None
    category: str | None = None


@router.get("")
async def list_memory(project_id: str | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    memories = await MemoryService(db).list(project_id=project_id)
    return {"memories": [memory.to_dict() for memory in memories]}


@router.post("")
async def create_memory(payload: MemoryCreate, db: AsyncSession = Depends(get_db)):
    memory = await MemoryService(db).record(
        project_id=payload.projectId,
        scope=payload.scope,
        category=payload.category,
        content=payload.content,
        rationale=payload.rationale,
    )
    return memory.to_dict()


@router.put("/{memory_id}")
async def update_memory(memory_id: str, payload: MemoryUpdate, db: AsyncSession = Depends(get_db)):
    memory = await MemoryService(db).update(memory_id, payload.model_dump(exclude_unset=True))
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory.to_dict()


@router.get("/search")
async def search_memory(query: str, project_id: str | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    memories = await MemoryService(db).search(project_id=project_id, query=query)
    return {"memories": [memory.to_dict() for memory in memories]}
