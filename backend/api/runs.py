from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Task, TaskRun
from services.artifact_store import ArtifactStore
from services.task_dependencies import build_task_dependency_state, load_tasks_by_id
from services.run_engine import RunEngine


router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TaskRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return run.to_dict()


@router.get("/{run_id}/artifacts")
async def get_run_artifacts(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TaskRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    artifacts = await ArtifactStore(db).list_for_run(run_id)
    return {"artifacts": [artifact.to_dict() for artifact in artifacts]}


@router.post("/{run_id}/adopt")
async def adopt_run(run_id: str, db: AsyncSession = Depends(get_db)):
    return await RunEngine(db).adopt_run(run_id)


@router.post("/{run_id}/retry")
async def retry_run(run_id: str, db: AsyncSession = Depends(get_db)):
    task_run = await db.get(TaskRun, run_id)
    if task_run is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    task = await db.get(Task, task_run.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    dependency_state = build_task_dependency_state(task, await load_tasks_by_id(db))
    if not dependency_state.ready:
        raise HTTPException(status_code=409, detail=dependency_state.summary or "当前任务仍被依赖阻塞")
    run = await RunEngine(db).retry_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return run.to_dict()
