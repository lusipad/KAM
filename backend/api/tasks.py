from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import get_db
from models import Task, TaskRef, TaskRun, now
from services.task_dispatcher import TaskDispatcherService
from services.task_autodrive import GlobalAutoDriveService, TaskAutoDriveService
from services.run_engine import RunEngine
from services.task_planner import TaskPlannerService
from services.task_context import TaskContextService


router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskRefCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    metadata: dict[str, Any] | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    repoPath: str | None = Field(default=None, max_length=500)
    status: str = Field(default="open", max_length=20)
    priority: str = Field(default="medium", max_length=20)
    labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    refs: list[TaskRefCreate] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    repoPath: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=20)
    priority: str | None = Field(default=None, max_length=20)
    labels: list[str] | None = None


class TaskResolveContext(BaseModel):
    focus: str | None = Field(default=None, max_length=2000)


class TaskRunCreate(BaseModel):
    agent: str = Field(pattern="^(codex|claude-code)$")
    task: str = Field(min_length=1, max_length=8000)


class TaskPlanCreate(BaseModel):
    createTasks: bool = True
    limit: int = Field(default=3, ge=1, le=5)


class TaskDispatchCreate(BaseModel):
    createPlanIfNeeded: bool = True


class TaskContinueCreate(BaseModel):
    taskId: str | None = None
    createPlanIfNeeded: bool = True


@router.get("")
async def list_tasks(
    include_archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Task).order_by(desc(Task.updated_at))
    if not include_archived:
        stmt = stmt.where(Task.archived_at.is_(None))
    result = await db.execute(stmt)
    return {"tasks": [task.to_dict() for task in result.scalars()]}


@router.post("/dispatch-next")
async def dispatch_next_task(payload: TaskDispatchCreate, db: AsyncSession = Depends(get_db)):
    dispatched = await TaskDispatcherService(db).dispatch_next(create_plan_if_needed=payload.createPlanIfNeeded)
    if dispatched is None:
        raise HTTPException(status_code=409, detail="当前没有可自动接手的任务")
    return dispatched.to_dict()


@router.post("/continue")
async def continue_task(payload: TaskContinueCreate, db: AsyncSession = Depends(get_db)):
    if payload.taskId is not None:
        task = await db.get(Task, payload.taskId)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
    result = await TaskDispatcherService(db).continue_task(
        task_id=payload.taskId,
        create_plan_if_needed=payload.createPlanIfNeeded,
    )
    return result.to_dict()


@router.post("/{task_id}/autodrive/start")
async def start_task_autodrive(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await TaskAutoDriveService(db).start(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result.to_dict()


@router.post("/{task_id}/autodrive/stop")
async def stop_task_autodrive(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await TaskAutoDriveService(db).stop(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result.to_dict()


@router.get("/autodrive/global")
async def get_global_autodrive_status(db: AsyncSession = Depends(get_db)):
    return (await GlobalAutoDriveService(db).get_status()).to_dict()


@router.post("/autodrive/global/start")
async def start_global_autodrive(db: AsyncSession = Depends(get_db)):
    return (await GlobalAutoDriveService(db).start()).to_dict()


@router.post("/autodrive/global/stop")
async def stop_global_autodrive(db: AsyncSession = Depends(get_db)):
    return (await GlobalAutoDriveService(db).stop()).to_dict()


@router.post("")
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    metadata = dict(payload.metadata or {}) or None
    dedup_key = _source_dedup_key(metadata)
    if dedup_key:
        reusable_task = await _find_reusable_source_task(db, dedup_key)
        if reusable_task is not None:
            reusable_task.title = payload.title.strip()
            reusable_task.description = payload.description.strip() if payload.description else None
            reusable_task.repo_path = payload.repoPath.strip() if payload.repoPath else None
            reusable_task.priority = payload.priority.strip()
            reusable_task.labels = _merge_labels(reusable_task.labels or [], payload.labels)
            reusable_task.metadata_ = _merge_task_metadata(reusable_task.metadata_ or {}, metadata)
            await _refresh_source_refs(db, reusable_task, payload.refs, metadata)
            reusable_task.updated_at = now()
            await db.commit()
            await db.refresh(reusable_task)
            return reusable_task.to_dict()

    task = Task(
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        repo_path=payload.repoPath.strip() if payload.repoPath else None,
        status=payload.status.strip(),
        priority=payload.priority.strip(),
        labels=[label.strip() for label in payload.labels if label.strip()],
        metadata_=metadata,
    )
    db.add(task)
    await db.flush()
    _add_task_refs(db, task.id, payload.refs)
    await db.commit()
    await db.refresh(task)
    return task.to_dict()


def _source_dedup_key(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    value = metadata.get("sourceDedupKey")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _merge_labels(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    for raw in [*existing, *incoming]:
        label = raw.strip()
        if label and label not in merged:
            merged.append(label)
    return merged


def _merge_task_metadata(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged.update(incoming)
    return merged


async def _find_reusable_source_task(db: AsyncSession, dedup_key: str) -> Task | None:
    result = await db.execute(
        select(Task)
        .where(Task.archived_at.is_(None))
        .where(Task.status.in_(("open", "in_progress")))
        .where(Task.metadata_["sourceDedupKey"].as_string() == dedup_key)
        .where(~Task.runs.any())
        .options(selectinload(Task.refs))
        .order_by(desc(Task.updated_at))
        .limit(1)
    )
    return result.scalars().first()


async def _refresh_source_refs(
    db: AsyncSession,
    task: Task,
    refs: list[TaskRefCreate],
    metadata: dict[str, Any],
) -> None:
    intake_source_kind = str(metadata.get("sourceKind") or "").strip()
    existing_refs = list(task.refs)
    for ref in existing_refs:
        ref_source_kind = str((ref.metadata_ or {}).get("intakeSourceKind") or "").strip()
        if intake_source_kind and ref_source_kind == intake_source_kind:
            await db.delete(ref)
    _add_task_refs(db, task.id, refs)


def _add_task_refs(db: AsyncSession, task_id: str, refs: list[TaskRefCreate]) -> None:
    for ref_payload in refs:
        db.add(
            TaskRef(
                task_id=task_id,
                kind=ref_payload.kind.strip(),
                label=ref_payload.label.strip(),
                value=ref_payload.value.strip(),
                metadata_=ref_payload.metadata,
            )
        )


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await _load_task_detail(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    runs = await _list_task_runs(db, task)
    state = sa_inspect(task)
    compares = [] if "review_compares" in state.unloaded else [compare.to_dict() for compare in task.review_compares]
    return {
        **task.to_detail_dict(),
        "runs": [run.to_dict() for run in runs],
        "reviews": compares,
    }


@router.patch("/{task_id}")
async def update_task(task_id: str, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if payload.title is not None:
        task.title = payload.title.strip()
    if payload.description is not None:
        task.description = payload.description.strip() or None
    if payload.repoPath is not None:
        task.repo_path = payload.repoPath.strip() or None
    if payload.status is not None:
        task.status = payload.status.strip()
    if payload.priority is not None:
        task.priority = payload.priority.strip()
    if payload.labels is not None:
        task.labels = [label.strip() for label in payload.labels if label.strip()]
    task.updated_at = now()
    await db.commit()
    await db.refresh(task)
    return task.to_dict()


@router.post("/{task_id}/archive")
async def archive_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.archived_at = now()
    task.status = "archived"
    task.updated_at = task.archived_at
    await db.commit()
    await db.refresh(task)
    return task.to_dict()


@router.post("/{task_id}/refs")
async def add_task_ref(task_id: str, payload: TaskRefCreate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    ref = TaskRef(
        task_id=task.id,
        kind=payload.kind.strip(),
        label=payload.label.strip(),
        value=payload.value.strip(),
        metadata_=payload.metadata,
    )
    db.add(ref)
    task.updated_at = now()
    await db.commit()
    await db.refresh(ref)
    return ref.to_dict()


@router.delete("/{task_id}/refs/{ref_id}")
async def delete_task_ref(task_id: str, ref_id: str, db: AsyncSession = Depends(get_db)):
    ref = await db.get(TaskRef, ref_id)
    if ref is None or ref.task_id != task_id:
        raise HTTPException(status_code=404, detail="引用不存在")
    await db.delete(ref)
    task = await db.get(Task, task_id)
    if task is not None:
        task.updated_at = now()
    await db.commit()
    return {"ok": True}


@router.post("/{task_id}/context/resolve")
async def resolve_task_context(task_id: str, payload: TaskResolveContext, db: AsyncSession = Depends(get_db)):
    snapshot = await TaskContextService(db).build_snapshot(task_id, focus=payload.focus)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return snapshot.to_dict()


@router.post("/{task_id}/runs")
async def create_task_run(task_id: str, payload: TaskRunCreate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    run_engine = RunEngine(db)
    run = await run_engine.create_task_run(
        task_id=task.id,
        agent=payload.agent,
        task=payload.task.strip(),
        initial_artifacts=await run_engine.build_task_initial_artifacts(task.id),
    )
    task.updated_at = now()
    await db.commit()
    return run.to_dict()


@router.post("/{task_id}/plan")
async def plan_task_follow_ups(task_id: str, payload: TaskPlanCreate, db: AsyncSession = Depends(get_db)):
    planner = TaskPlannerService(db)
    plan = await planner.plan_follow_ups(task_id, create_tasks=payload.createTasks, limit=payload.limit)
    if plan is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return plan


async def _load_task_detail(db: AsyncSession, task_id: str) -> Task | None:
    stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.refs),
            selectinload(Task.snapshots),
            selectinload(Task.review_compares),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def _list_task_runs(db: AsyncSession, task: Task) -> list[TaskRun]:
    result = await db.execute(select(TaskRun).where(TaskRun.task_id == task.id).order_by(TaskRun.created_at.asc()))
    return list(result.scalars())
