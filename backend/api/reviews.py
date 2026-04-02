from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services.review_compare import ReviewCompareService


router = APIRouter(prefix="/reviews", tags=["reviews"])


class CompareCreate(BaseModel):
    runIds: list[str] = Field(min_length=2)
    title: str | None = Field(default=None, max_length=200)


@router.post("/{task_id}/compare")
async def create_compare(task_id: str, payload: CompareCreate, db: AsyncSession = Depends(get_db)):
    try:
        compare = await ReviewCompareService(db).create(
            task_id,
            payload.runIds,
            title=payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if compare is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return compare.to_dict()
