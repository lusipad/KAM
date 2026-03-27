from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services.watcher import watcher_engine


router = APIRouter(prefix="/watchers", tags=["watchers"])


class WatcherCreate(BaseModel):
    projectId: str
    name: str = Field(min_length=1, max_length=200)
    sourceType: str
    config: dict
    scheduleType: str = "interval"
    scheduleValue: str = "15m"
    autoActionLevel: int = 1


@router.get("")
async def list_watchers(db: AsyncSession = Depends(get_db)):
    watchers = await watcher_engine.list_watchers(db)
    return {"watchers": [watcher.to_dict() for watcher in watchers]}


@router.post("")
async def create_watcher(payload: WatcherCreate, db: AsyncSession = Depends(get_db)):
    watcher = await watcher_engine.create_watcher(
        db,
        project_id=payload.projectId,
        name=payload.name,
        source_type=payload.sourceType,
        config=payload.config,
        schedule_type=payload.scheduleType,
        schedule_value=payload.scheduleValue,
        auto_action_level=payload.autoActionLevel,
    )
    return watcher.to_dict()


@router.post("/{watcher_id}/pause")
async def pause_watcher(watcher_id: str, db: AsyncSession = Depends(get_db)):
    watcher = await watcher_engine.pause(db, watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher.to_dict()


@router.post("/{watcher_id}/resume")
async def resume_watcher(watcher_id: str, db: AsyncSession = Depends(get_db)):
    watcher = await watcher_engine.resume(db, watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher.to_dict()


@router.post("/{watcher_id}/run-now")
async def run_watcher_now(watcher_id: str, db: AsyncSession = Depends(get_db)):
    event = await watcher_engine.run_now(db, watcher_id)
    return {"event": event.to_dict() if event else None}


@router.post("/events/{event_id}/actions/{action_index}")
async def execute_event_action(event_id: str, action_index: int, db: AsyncSession = Depends(get_db)):
    return await watcher_engine.execute_action(db, event_id, action_index)


@router.post("/events/{event_id}/dismiss")
async def dismiss_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await watcher_engine.dismiss_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Watcher event not found")
    return event.to_dict()
