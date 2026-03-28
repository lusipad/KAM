from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Run
from services.run_engine import RunEngine


router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return run.to_dict()


@router.post("/{run_id}/adopt")
async def adopt_run(run_id: str, db: AsyncSession = Depends(get_db)):
    return await RunEngine(db).adopt_run(run_id)


@router.post("/{run_id}/retry")
async def retry_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await RunEngine(db).retry_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return run.to_dict()
