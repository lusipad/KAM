from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import ContextSnapshot


router = APIRouter(prefix="/context/snapshots", tags=["context"])


@router.get("/{snapshot_id}")
async def get_context_snapshot(snapshot_id: str, db: AsyncSession = Depends(get_db)):
    snapshot = await db.get(ContextSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="上下文快照不存在")
    return snapshot.to_dict()
