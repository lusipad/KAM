from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Task, TaskRun, now
from services.run_engine import RunEngine
from services.task_planner import TaskPlannerService


@dataclass
class TaskDispatchResult:
    task: Task
    run: TaskRun
    source: str
    planned_from_task_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task.to_dict(),
            "run": self.run.to_dict(),
            "source": self.source,
            "plannedFromTaskId": self.planned_from_task_id,
        }


class TaskDispatcherService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dispatch_next(self, *, create_plan_if_needed: bool = True) -> TaskDispatchResult | None:
        selected_task, source, planned_from_task_id = await self._pick_next_task(create_plan_if_needed=create_plan_if_needed)
        if selected_task is None:
            return None

        metadata = selected_task.metadata_ or {}
        prompt = self._recommended_prompt(metadata)
        if not prompt:
            return None

        recommended_agent = self._recommended_agent(metadata)
        if selected_task.status == "open":
            selected_task.status = "in_progress"
        selected_task.updated_at = now()

        run_engine = RunEngine(self.db)
        run = await run_engine.create_task_run(
            task_id=selected_task.id,
            agent=recommended_agent,
            task=prompt,
            initial_artifacts=await run_engine.build_task_initial_artifacts(selected_task.id),
        )
        await self.db.refresh(selected_task)
        return TaskDispatchResult(
            task=selected_task,
            run=run,
            source=source,
            planned_from_task_id=planned_from_task_id,
        )

    async def _pick_next_task(self, *, create_plan_if_needed: bool) -> tuple[Task | None, str, str | None]:
        tasks = await self._list_tasks()
        existing = self._pick_existing_runnable_task(tasks)
        if existing is not None:
            return existing, "existing_task", None

        if not create_plan_if_needed:
            return None, "existing_task", None

        parent = self._pick_parent_for_planning(tasks)
        if parent is None:
            return None, "planned_task", None

        _task, _suggestions, created_tasks = await TaskPlannerService(self.db).plan(
            parent.id,
            limit=1,
            create_tasks=True,
        )
        if created_tasks:
            return created_tasks[0], "planned_task", parent.id

        refreshed_tasks = await self._list_tasks()
        existing = self._pick_existing_runnable_task(refreshed_tasks)
        if existing is not None:
            return existing, "existing_task", None
        return None, "planned_task", parent.id

    async def _list_tasks(self) -> list[Task]:
        result = await self.db.execute(
            select(Task)
            .where(Task.archived_at.is_(None))
            .options(selectinload(Task.runs))
            .order_by(Task.updated_at.desc())
        )
        return list(result.scalars())

    def _pick_existing_runnable_task(self, tasks: list[Task]) -> Task | None:
        candidates = [task for task in tasks if self._is_runnable_existing_task(task)]
        if not candidates:
            return None
        candidates.sort(key=self._existing_task_sort_key)
        return candidates[0]

    def _pick_parent_for_planning(self, tasks: list[Task]) -> Task | None:
        candidates = [task for task in tasks if self._is_plannable_parent_task(task)]
        if not candidates:
            return None
        candidates.sort(key=self._parent_task_sort_key)
        return candidates[0]

    def _is_runnable_existing_task(self, task: Task) -> bool:
        if self._is_terminal_task(task):
            return False
        if not self._recommended_prompt(task.metadata_ or {}):
            return False
        if any(run.status in {"pending", "running"} for run in task.runs):
            return False
        latest_run = task.runs[-1] if task.runs else None
        if latest_run is not None and latest_run.status == "passed":
            return False
        return True

    def _is_plannable_parent_task(self, task: Task) -> bool:
        if self._is_terminal_task(task):
            return False
        if (task.metadata_ or {}).get("parentTaskId"):
            return False
        if any(run.status in {"pending", "running"} for run in task.runs):
            return False
        return task.status in {"open", "in_progress", "failed"}

    def _existing_task_sort_key(self, task: Task) -> tuple[int, int, int, float]:
        latest_run = task.runs[-1] if task.runs else None
        run_rank = 0 if latest_run is not None and latest_run.status == "failed" else 1
        child_rank = 0 if (task.metadata_ or {}).get("parentTaskId") else 1
        return (
            run_rank,
            child_rank,
            self._priority_rank(task.priority),
            -task.updated_at.timestamp(),
        )

    def _parent_task_sort_key(self, task: Task) -> tuple[int, int, float]:
        status_rank = 0 if task.status == "in_progress" else 1
        return (
            status_rank,
            self._priority_rank(task.priority),
            -task.updated_at.timestamp(),
        )

    def _is_terminal_task(self, task: Task) -> bool:
        return task.status in {"archived", "done", "verified", "blocked"}

    def _priority_rank(self, priority: str | None) -> int:
        normalized = (priority or "").strip().lower()
        if normalized == "high":
            return 0
        if normalized == "medium":
            return 1
        if normalized == "low":
            return 2
        return 3

    def _recommended_prompt(self, metadata: dict[str, object]) -> str:
        value = metadata.get("recommendedPrompt")
        return value.strip() if isinstance(value, str) else ""

    def _recommended_agent(self, metadata: dict[str, object]) -> str:
        value = metadata.get("recommendedAgent")
        return "claude-code" if value == "claude-code" else "codex"
