"""
KAM v2 Run API
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, get_db
from app.services.run_engine import TERMINAL_RUN_STATUSES
from app.services.run_service import RunService

router = APIRouter(prefix="/v2", tags=["v2-runs"])


class RunCreate(BaseModel):
    agent: Optional[str] = None
    command: Optional[str] = None
    prompt: str = ""
    model: Optional[str] = None
    reasoningEffort: Optional[str] = None
    maxRounds: int = Field(default=5, ge=1, le=12)
    autoStart: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompareAgentCreate(BaseModel):
    agent: str = Field(..., min_length=1, max_length=50)
    label: Optional[str] = None
    command: Optional[str] = None
    model: Optional[str] = None
    reasoningEffort: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompareCreate(BaseModel):
    prompt: str = Field(..., min_length=1)
    agents: list[CompareAgentCreate] = Field(..., min_length=2, max_length=4)
    maxRounds: int = Field(default=5, ge=1, le=12)
    autoStart: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/threads/{thread_id}/runs")
async def list_thread_runs(thread_id: str, db: Session = Depends(get_db)):
    service = RunService(db)
    return {"runs": [run.to_dict(include_artifacts=False) for run in service.list_runs(thread_id)]}


@router.post("/threads/{thread_id}/runs")
async def create_thread_run(thread_id: str, data: RunCreate, db: Session = Depends(get_db)):
    service = RunService(db)
    payload = data.model_dump()
    auto_start = payload.pop("autoStart", True)
    run = service.create_run(thread_id, payload, auto_start=auto_start)
    if not run:
        raise HTTPException(status_code=404, detail="线程不存在")
    return run.to_dict()


@router.post("/threads/{thread_id}/compare")
async def compare_thread_runs(thread_id: str, data: CompareCreate, db: Session = Depends(get_db)):
    service = RunService(db)
    result = service.compare_runs(thread_id, data.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="线程不存在或 compare 参数无效")
    return result


@router.post("/runs/{run_id}/start")
async def start_run(run_id: str, db: Session = Depends(get_db)):
    service = RunService(db)
    run = service.start_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict(include_artifacts=False)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: Session = Depends(get_db)):
    service = RunService(db)
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict()


@router.get("/runs/{run_id}/artifacts")
async def get_run_artifacts(
    run_id: str,
    tail_chars: Optional[int] = Query(default=None, ge=200, le=500_000),
    db: Session = Depends(get_db),
):
    service = RunService(db)
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    artifacts = service.list_artifacts(run_id)
    return {"artifacts": [service.hydrate_artifact(artifact, max_chars=tail_chars) for artifact in artifacts]}


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    tail_chars: int = Query(default=20_000, ge=200, le=500_000),
    db: Session = Depends(get_db),
):
    service = RunService(db)
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
                stream_service = RunService(stream_db)
                current_run = stream_service.get_run(run_id)
                if not current_run:
                    break

                artifacts = [
                    stream_service.hydrate_artifact(artifact, max_chars=tail_chars)
                    for artifact in stream_service.list_artifacts(run_id)
                ]
                payload = {
                    "run": current_run.to_dict(include_artifacts=False),
                    "artifacts": artifacts,
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


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, db: Session = Depends(get_db)):
    service = RunService(db)
    run = service.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict(include_artifacts=False)


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: str, db: Session = Depends(get_db)):
    service = RunService(db)
    run = service.retry_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict()


@router.post("/runs/{run_id}/adopt")
async def adopt_run(run_id: str, db: Session = Depends(get_db)):
    service = RunService(db)
    run = service.adopt_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run.to_dict(include_artifacts=False)
