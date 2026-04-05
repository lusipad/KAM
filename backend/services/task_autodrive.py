from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import async_session
from models import Task, now


AUTO_DRIVE_ENABLED_KEY = "autoDriveEnabled"
AUTO_DRIVE_STATUS_KEY = "autoDriveStatus"
AUTO_DRIVE_LOOP_COUNT_KEY = "autoDriveLoopCount"
AUTO_DRIVE_LAST_ACTION_KEY = "autoDriveLastAction"
AUTO_DRIVE_LAST_REASON_KEY = "autoDriveLastReason"
AUTO_DRIVE_LAST_SUMMARY_KEY = "autoDriveLastSummary"
AUTO_DRIVE_LAST_DECISION_AT_KEY = "autoDriveLastDecisionAt"
AUTO_DRIVE_LAST_RUN_ID_KEY = "autoDriveLastRunId"
AUTO_DRIVE_LAST_RUN_TASK_ID_KEY = "autoDriveLastRunTaskId"
AUTO_DRIVE_LAST_ERROR_KEY = "autoDriveLastError"

AUTO_DRIVE_MAX_STEPS = 8


@dataclass
class AutoDriveControlResult:
    task: Task
    scope_task_id: str
    enabled: bool
    running: bool
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task.to_dict(),
            "scopeTaskId": self.scope_task_id,
            "enabled": self.enabled,
            "running": self.running,
            "summary": self.summary,
        }


@dataclass
class _AutoDriveState:
    scopes: dict[str, asyncio.Future[None]] = field(default_factory=dict)


_STATE = _AutoDriveState()


class TaskAutoDriveService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def start(self, task_id: str) -> AutoDriveControlResult | None:
        scope_task = await self.load_scope_root(task_id)
        if scope_task is None:
            return None
        self._update_scope_metadata(
            scope_task,
            enabled=True,
            status="running",
            summary="已开启当前任务族的自动托管。",
            error="",
        )
        scope_task.updated_at = now()
        await self.db.commit()
        started = await ensure_scope_autodrive(scope_task.id)
        await self.db.refresh(scope_task)
        return AutoDriveControlResult(
            task=scope_task,
            scope_task_id=scope_task.id,
            enabled=True,
            running=is_scope_autodrive_running(scope_task.id),
            summary="已开启当前任务族的自动托管。" if started else "当前任务族已经处于自动托管中。",
        )

    async def stop(self, task_id: str) -> AutoDriveControlResult | None:
        scope_task = await self.load_scope_root(task_id)
        if scope_task is None:
            return None
        self._update_scope_metadata(
            scope_task,
            enabled=False,
            status="disabled",
            summary="已停止当前任务族的自动托管。",
            error="",
        )
        scope_task.updated_at = now()
        await self.db.commit()
        await self.db.refresh(scope_task)
        return AutoDriveControlResult(
            task=scope_task,
            scope_task_id=scope_task.id,
            enabled=False,
            running=is_scope_autodrive_running(scope_task.id),
            summary="已停止当前任务族的自动托管。",
        )

    async def load_scope_root(self, task_id: str) -> Task | None:
        task = await self.db.get(Task, task_id)
        if task is None:
            return None
        parent_task_id = self._scope_parent_task_id(task)
        if parent_task_id is None:
            return task
        parent_task = await self.db.get(Task, parent_task_id)
        return parent_task or task

    def is_enabled(self, task: Task | None) -> bool:
        if task is None:
            return False
        return bool((task.metadata_ or {}).get(AUTO_DRIVE_ENABLED_KEY))

    def _scope_parent_task_id(self, task: Task) -> str | None:
        value = (task.metadata_ or {}).get("parentTaskId")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _update_scope_metadata(
        self,
        task: Task,
        *,
        enabled: bool | None = None,
        status: str | None = None,
        action: str | None = None,
        reason: str | None = None,
        summary: str | None = None,
        run_id: str | None = None,
        run_task_id: str | None = None,
        error: str | None = None,
        increment_loop_count: bool = False,
    ) -> None:
        metadata = dict(task.metadata_ or {})
        if enabled is not None:
            metadata[AUTO_DRIVE_ENABLED_KEY] = enabled
        if status is not None:
            metadata[AUTO_DRIVE_STATUS_KEY] = status
        if increment_loop_count:
            current = metadata.get(AUTO_DRIVE_LOOP_COUNT_KEY)
            count = current if isinstance(current, int) else 0
            metadata[AUTO_DRIVE_LOOP_COUNT_KEY] = count + 1
        if action is not None:
            metadata[AUTO_DRIVE_LAST_ACTION_KEY] = action
        if reason is not None:
            metadata[AUTO_DRIVE_LAST_REASON_KEY] = reason
        if summary is not None:
            metadata[AUTO_DRIVE_LAST_SUMMARY_KEY] = summary
        if any(item is not None for item in (action, reason, summary)):
            metadata[AUTO_DRIVE_LAST_DECISION_AT_KEY] = now().isoformat()
        if run_id is not None:
            metadata[AUTO_DRIVE_LAST_RUN_ID_KEY] = run_id
        if run_task_id is not None:
            metadata[AUTO_DRIVE_LAST_RUN_TASK_ID_KEY] = run_task_id
        if error is not None:
            if error:
                metadata[AUTO_DRIVE_LAST_ERROR_KEY] = error
            else:
                metadata.pop(AUTO_DRIVE_LAST_ERROR_KEY, None)
        task.metadata_ = metadata


def is_scope_autodrive_running(scope_task_id: str) -> bool:
    task = _STATE.scopes.get(scope_task_id)
    return task is not None and not task.done()


async def schedule_autodrive_for_task(task_id: str | None) -> str | None:
    if task_id is None:
        return None
    async with async_session() as session:
        service = TaskAutoDriveService(session)
        scope_task = await service.load_scope_root(task_id)
        if scope_task is None or not service.is_enabled(scope_task):
            return None
        scope_task_id = scope_task.id
    await ensure_scope_autodrive(scope_task_id)
    return scope_task_id


async def ensure_scope_autodrive(scope_task_id: str) -> bool:
    current = _STATE.scopes.get(scope_task_id)
    if current is not None and not current.done():
        return False
    if settings.is_test_env:
        return await _run_scope_autodrive(scope_task_id)
    return schedule_scope_autodrive(scope_task_id)


def schedule_scope_autodrive(scope_task_id: str) -> bool:
    current = _STATE.scopes.get(scope_task_id)
    if current is not None and not current.done():
        return False

    background_task = asyncio.create_task(_run_scope_autodrive(scope_task_id))
    _STATE.scopes[scope_task_id] = background_task

    def _cleanup(done_task: asyncio.Task[None]) -> None:
        current_task = _STATE.scopes.get(scope_task_id)
        if current_task is done_task:
            _STATE.scopes.pop(scope_task_id, None)

    background_task.add_done_callback(_cleanup)
    return True


async def _run_scope_autodrive(scope_task_id: str) -> bool:
    if settings.is_test_env:
        marker = asyncio.get_running_loop().create_future()
        marker.set_result(None)
        _STATE.scopes[scope_task_id] = marker
    try:
        for _ in range(AUTO_DRIVE_MAX_STEPS):
            async with async_session() as session:
                service = TaskAutoDriveService(session)
                scope_task = await service.load_scope_root(scope_task_id)
                if scope_task is None or not service.is_enabled(scope_task):
                    return True

                from services.task_dispatcher import TaskDispatcherService

                decision = await TaskDispatcherService(session).continue_task(
                    task_id=scope_task_id,
                    create_plan_if_needed=True,
                )
                enabled = True
                status = "running"
                if decision.action == "stop":
                    if decision.reason == "scope_has_active_run":
                        status = "waiting_for_run"
                    elif decision.reason in {"scope_task_terminal", "task_not_found"}:
                        enabled = False
                        status = "disabled"
                    else:
                        status = "idle"
                elif decision.run is not None and decision.run.status in {"pending", "running"}:
                    status = "waiting_for_run"

                service._update_scope_metadata(
                    scope_task,
                    enabled=enabled,
                    status=status,
                    action=decision.action,
                    reason=decision.reason,
                    summary=decision.summary,
                    run_id=decision.run.id if decision.run is not None else None,
                    run_task_id=decision.run.task_id if decision.run is not None else None,
                    error="",
                    increment_loop_count=True,
                )
                scope_task.updated_at = now()
                await session.commit()

                if not _should_continue_immediately(decision):
                    return True

            await asyncio.sleep(0)

        async with async_session() as session:
            service = TaskAutoDriveService(session)
            scope_task = await service.load_scope_root(scope_task_id)
            if scope_task is None or not service.is_enabled(scope_task):
                return True
            service._update_scope_metadata(
                scope_task,
                status="paused",
                action="stop",
                reason="auto_drive_step_limit_reached",
                summary="自动托管达到单轮步数上限，等待新的 run 结果或再次启动。",
                error="",
            )
            scope_task.updated_at = now()
            await session.commit()
        return True
    except Exception as exc:
        async with async_session() as session:
            service = TaskAutoDriveService(session)
            scope_task = await service.load_scope_root(scope_task_id)
            if scope_task is None:
                return True
            service._update_scope_metadata(
                scope_task,
                status="error",
                summary=f"自动托管异常中断：{type(exc).__name__}",
                error=f"{type(exc).__name__}: {exc}",
            )
            scope_task.updated_at = now()
            await session.commit()
        return True
    finally:
        if settings.is_test_env:
            _STATE.scopes.pop(scope_task_id, None)


def _should_continue_immediately(decision: Any) -> bool:
    if decision.action == "adopt":
        return True
    if decision.action == "stop":
        return False
    if decision.run is None:
        return False
    return decision.run.status in {"passed", "failed"}


async def wait_for_background_autodrive(timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        current_loop = asyncio.get_running_loop()
        pending = [
            task
            for task in _STATE.scopes.values()
            if not task.done() and task.get_loop() is current_loop
        ]
        if not pending:
            return
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            return
        done, still_pending = await asyncio.wait(pending, timeout=remaining)
        if done:
            await asyncio.gather(*done, return_exceptions=True)
        if not still_pending:
            continue
        for task in still_pending:
            task.cancel()
        await asyncio.gather(*still_pending, return_exceptions=True)
        return
