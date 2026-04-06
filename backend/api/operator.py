from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services.operator_control import OperatorControlService


router = APIRouter(prefix="/operator", tags=["operator"])


class OperatorActionRequest(BaseModel):
    action: Literal[
        "start_global_autodrive",
        "stop_global_autodrive",
        "restart_global_autodrive",
        "dispatch_next",
        "continue_task_family",
        "start_task_autodrive",
        "stop_task_autodrive",
        "adopt_run",
        "retry_run",
        "cancel_run",
    ]
    taskId: str | None = None
    runId: str | None = None


@router.get("/control-plane")
async def get_operator_control_plane(
    task_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return (await OperatorControlService(db).get_control_plane(task_id=task_id)).to_dict()


@router.post("/actions")
async def perform_operator_action(payload: OperatorActionRequest, db: AsyncSession = Depends(get_db)):
    return (
        await OperatorControlService(db).perform_action(
            action=payload.action,
            task_id=payload.taskId,
            run_id=payload.runId,
        )
    ).to_dict()
