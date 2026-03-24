"""
Lite 任务台 API
"""
import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, get_db
from app.services.workspace_service import WorkspaceService

router = APIRouter(tags=["workspace"])
TERMINAL_RUN_STATUSES = {"completed", "failed", "canceled"}


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    status: str = "inbox"
    priority: str = "medium"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class RefCreate(BaseModel):
    type: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunAgentInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = "custom"
    command: Optional[str] = None


class RunCreate(BaseModel):
    agents: list[RunAgentInput]


@router.get("/tasks")
async def get_tasks(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = WorkspaceService(db)
    tasks = service.list_tasks(status=status)
    return {"tasks": [task.to_dict() for task in tasks]}


@router.post("/tasks")
async def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    task = service.create_task(data.model_dump())
    return task.to_dict()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    task = service.update_task(task_id, data.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


@router.post("/tasks/{task_id}/archive")
async def archive_task(task_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    task = service.archive_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


@router.post("/tasks/{task_id}/refs")
async def add_task_ref(task_id: str, data: RefCreate, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    ref = service.add_task_ref(task_id, data.model_dump())
    if not ref:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ref.to_dict()


@router.delete("/tasks/{task_id}/refs/{ref_id}")
async def delete_task_ref(task_id: str, ref_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    deleted = service.delete_task_ref(task_id, ref_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="引用不存在")
    return {"message": "引用已删除"}


@router.post("/tasks/{task_id}/context/resolve")
async def resolve_context(task_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    snapshot = service.resolve_context(task_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="任务不存在")
    return snapshot.to_dict()


@router.get("/context/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    snapshot = service.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="上下文快照不存在")
    return snapshot.to_dict()


@router.post("/tasks/{task_id}/runs")
async def create_runs(task_id: str, data: RunCreate, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    runs = service.create_runs(task_id, [agent.model_dump() for agent in data.agents])
    if runs is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"runs": [run.to_dict() for run in runs]}


@router.get("/runs")
async def get_runs(
    task_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = WorkspaceService(db)
    runs = service.list_runs(task_id=task_id, status=status)
    return {"runs": [run.to_dict(include_artifacts=False) for run in runs]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict()


@router.post("/runs/{run_id}/start")
async def start_run(run_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    run = service.start_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict(include_artifacts=False)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    run = service.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict()


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    run = service.retry_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict()


@router.post("/runs/{run_id}/apply-patch")
async def apply_run_patch(run_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    try:
        result = service.apply_patch_from_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return result


@router.get("/runs/{run_id}/artifacts")
async def get_run_artifacts(
    run_id: str,
    tail_chars: Optional[int] = Query(default=None, ge=200, le=500_000),
    db: Session = Depends(get_db),
):
    service = WorkspaceService(db)
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return {"artifacts": [service.hydrate_artifact(artifact, max_chars=tail_chars) for artifact in run.artifacts]}


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    tail_chars: int = Query(default=20_000, ge=200, le=500_000),
    db: Session = Depends(get_db),
):
    service = WorkspaceService(db)
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")

    async def event_stream():
        last_payload: str | None = None

        while True:
            if await request.is_disconnected():
                break

            stream_db = SessionLocal()
            try:
                stream_service = WorkspaceService(stream_db)
                current_run = stream_service.get_run(run_id)
                if not current_run:
                    break

                payload = {
                    "run": current_run.to_dict(include_artifacts=False),
                    "artifacts": [
                        stream_service.hydrate_artifact(artifact, max_chars=tail_chars)
                        for artifact in current_run.artifacts
                    ],
                }
                serialized = json.dumps(payload, ensure_ascii=False)
                if serialized != last_payload:
                    last_payload = serialized
                    yield f"data: {serialized}\n\n"
                else:
                    yield ": keep-alive\n\n"

                if current_run.status in TERMINAL_RUN_STATUSES:
                    break
            finally:
                stream_db.close()

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/reviews/{task_id}")
async def get_review(task_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    review = service.get_review(task_id)
    if not review:
        raise HTTPException(status_code=404, detail="任务不存在")
    return review


@router.post("/reviews/{task_id}/summarize")
async def summarize_review(task_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    review = service.get_review(task_id)
    if not review:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"summary": review["summary"]}


@router.post("/reviews/{task_id}/compare")
async def compare_review(task_id: str, db: Session = Depends(get_db)):
    service = WorkspaceService(db)
    comparison = service.compare_runs(task_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"comparison": comparison}
