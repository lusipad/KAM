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


class WatcherUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    scheduleType: str | None = None
    scheduleValue: str | None = None
    autoActionLevel: int | None = Field(default=None, ge=1, le=3)


@router.get("")
async def list_watchers(db: AsyncSession = Depends(get_db)):
    watchers = await watcher_engine.list_watchers(db)
    return {"watchers": [watcher.to_dict() for watcher in watchers]}


@router.get("/{watcher_id}")
async def get_watcher(watcher_id: str, db: AsyncSession = Depends(get_db)):
    watcher = await watcher_engine.get_watcher(db, watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher.to_dict()


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


@router.put("/{watcher_id}")
async def update_watcher(watcher_id: str, payload: WatcherUpdate, db: AsyncSession = Depends(get_db)):
    watcher = await watcher_engine.update_watcher(
        db,
        watcher_id,
        name=payload.name.strip() if payload.name is not None else None,
        schedule_type=payload.scheduleType,
        schedule_value=payload.scheduleValue.strip() if payload.scheduleValue is not None else None,
        auto_action_level=payload.autoActionLevel,
    )
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher.to_dict()


@router.get("/{watcher_id}/events")
async def list_watcher_events(watcher_id: str, db: AsyncSession = Depends(get_db)):
    watcher = await watcher_engine.get_watcher(db, watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    events = await watcher_engine.list_events(db, watcher_id)
    return {"events": [event.to_dict() for event in events]}


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
