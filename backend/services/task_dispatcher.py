from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Task, TaskRun, now
from services.run_engine import RunEngine
from services.task_dependencies import build_task_dependency_state
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


@dataclass
class TaskContinueResult:
    action: str
    reason: str
    summary: str
    task: Task | None = None
    run: TaskRun | None = None
    source: str | None = None
    planned_from_task_id: str | None = None
    adopted_at: str | None = None
    scope_task_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "reason": self.reason,
            "summary": self.summary,
            "task": self.task.to_dict() if self.task is not None else None,
            "run": self.run.to_dict() if self.run is not None else None,
            "source": self.source,
            "plannedFromTaskId": self.planned_from_task_id,
            "adoptedAt": self.adopted_at,
            "scopeTaskId": self.scope_task_id,
            "error": self.error,
        }


@dataclass(frozen=True)
class _ContinueCandidate:
    action: str
    task: Task
    rank: tuple[int, ...]
    run: TaskRun | None = None
    source: str | None = None
    planned_from_task_id: str | None = None


class TaskDispatcherService:
    AUTO_RETRY_FAILURE_LIMIT = 2

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dispatch_next(
        self,
        *,
        create_plan_if_needed: bool = True,
        task_id: str | None = None,
    ) -> TaskDispatchResult | None:
        selected_task, source, planned_from_task_id = await self._pick_next_task(
            create_plan_if_needed=create_plan_if_needed,
            task_id=task_id,
        )
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

    async def continue_task(
        self,
        *,
        task_id: str | None = None,
        create_plan_if_needed: bool = True,
    ) -> TaskContinueResult:
        tasks = await self._list_tasks()
        tasks_by_id = {task.id: task for task in tasks}
        scoped_tasks = self._scope_tasks(tasks, task_id)
        scope_task_id = self._scope_root_task_id(tasks, task_id)
        if task_id is not None and not scoped_tasks:
            return TaskContinueResult(
                action="stop",
                reason="task_not_found",
                summary="目标任务不存在，无法继续自动推进。",
                scope_task_id=task_id,
            )

        scope_root = self._scope_root_task(tasks, task_id)
        if scope_root is not None and self._is_terminal_task(scope_root):
            return TaskContinueResult(
                action="stop",
                reason="scope_task_terminal",
                summary="当前任务已经收口，先停在这里。",
                task=scope_root,
                scope_task_id=scope_root.id,
            )
        if scope_root is not None:
            dependency_state = build_task_dependency_state(scope_root, tasks_by_id)
            if not dependency_state.ready:
                return TaskContinueResult(
                    action="stop",
                    reason="scope_dependencies_unresolved",
                    summary=dependency_state.summary or "当前任务仍被上游依赖阻塞，先不要继续自动推进。",
                    task=scope_root,
                    scope_task_id=scope_root.id,
                )
        if any(any(run.status in {"pending", "running"} for run in task.runs) for task in scoped_tasks):
            return TaskContinueResult(
                action="stop",
                reason="scope_has_active_run",
                summary="当前作用域里还有 run 在执行，先等待这轮结果。",
                task=scope_root,
                scope_task_id=scope_task_id,
            )

        candidate = self._pick_continue_candidate(
            scoped_tasks,
            create_plan_if_needed=create_plan_if_needed,
        )
        if candidate is None:
            return TaskContinueResult(
                action="stop",
                reason="no_high_value_action",
                summary="当前没有更高价值的自动下一步，先停在这里。",
                task=scope_root,
                scope_task_id=scope_task_id,
            )

        if candidate.action == "stop_retry_budget_exhausted" and candidate.run is not None:
            failed_task = candidate.task
            failed_run = candidate.run
            return TaskContinueResult(
                action="stop",
                reason="latest_failed_run_retry_budget_exhausted",
                summary=(
                    f"最近失败的 run {failed_run.id} 已达到自动重试上限，"
                    "先停下等待新的修复判断。"
                ),
                task=failed_task,
                run=failed_run,
                scope_task_id=scope_task_id,
            )

        if candidate.action == "adopt" and candidate.run is not None:
            adopt_task = candidate.task
            adopt_run = candidate.run
            adopt_result = await RunEngine(self.db).adopt_run(adopt_run.id)
            refreshed_task = await self.db.get(Task, adopt_task.id)
            refreshed_run = await self.db.get(TaskRun, adopt_run.id)
            if adopt_result.get("ok"):
                return TaskContinueResult(
                    action="adopt",
                    reason="latest_passed_run_adopted",
                    summary=f"已采纳最近通过的 run {adopt_run.id}。",
                    task=refreshed_task or adopt_task,
                    run=refreshed_run or adopt_run,
                    adopted_at=str(adopt_result.get("adoptedAt") or ""),
                    scope_task_id=scope_task_id,
                )
            return TaskContinueResult(
                action="stop",
                reason="adopt_failed",
                summary="当前 run 可以采纳，但自动采纳失败了。",
                task=refreshed_task or adopt_task,
                run=refreshed_run or adopt_run,
                scope_task_id=scope_task_id,
                error=str(adopt_result.get("error") or "adopt_failed"),
            )

        if candidate.action == "retry" and candidate.run is not None:
            retry_task = candidate.task
            failed_run = candidate.run
            failed_run_id = failed_run.id
            if retry_task.status == "open":
                retry_task.status = "in_progress"
            retry_task.updated_at = now()
            retried_run = await RunEngine(self.db).retry_run(failed_run.id)
            await self.db.refresh(retry_task)
            if retried_run is not None:
                return TaskContinueResult(
                    action="retry",
                    reason="latest_failed_run_retried",
                    summary=f"已自动重试最近失败的 run {failed_run_id}。",
                    task=retry_task,
                    run=retried_run,
                    scope_task_id=scope_task_id,
                )

        dispatched = await self.dispatch_next(
            create_plan_if_needed=candidate.action == "plan_parent",
            task_id=task_id,
        )
        if dispatched is None:
            return TaskContinueResult(
                action="stop",
                reason="no_high_value_action",
                summary="当前没有更高价值的自动下一步，先停在这里。",
                task=scope_root,
                scope_task_id=scope_task_id,
            )
        return TaskContinueResult(
            action="plan_and_dispatch",
            reason="dispatched_next_runnable_task",
            summary=(
                f"已先拆后跑：{dispatched.task.title}"
                if dispatched.source == "planned_task"
                else f"已接着推进现成任务：{dispatched.task.title}"
            ),
            task=dispatched.task,
            run=dispatched.run,
            source=dispatched.source,
            planned_from_task_id=dispatched.planned_from_task_id,
            scope_task_id=scope_task_id,
        )

    async def _pick_next_task(
        self,
        *,
        create_plan_if_needed: bool,
        task_id: str | None = None,
    ) -> tuple[Task | None, str, str | None]:
        tasks = self._scope_tasks(await self._list_tasks(), task_id)
        tasks_by_id = {task.id: task for task in tasks}
        existing = self._pick_existing_runnable_task(tasks, tasks_by_id)
        if existing is not None:
            return existing, "existing_task", None

        if not create_plan_if_needed:
            return None, "existing_task", None

        planning_candidates = self._pick_parents_for_planning(tasks, tasks_by_id)
        if not planning_candidates:
            return None, "planned_task", None

        last_parent_id: str | None = None
        for parent in planning_candidates:
            last_parent_id = parent.id
            _task, _suggestions, created_tasks = await TaskPlannerService(self.db).plan(
                parent.id,
                limit=1,
                create_tasks=True,
            )
            if created_tasks:
                return created_tasks[0], "planned_task", parent.id

            refreshed_tasks = await self._list_tasks()
            scoped_refreshed_tasks = self._scope_tasks(refreshed_tasks, task_id)
            refreshed_tasks_by_id = {task.id: task for task in scoped_refreshed_tasks}
            existing = self._pick_existing_runnable_task(scoped_refreshed_tasks, refreshed_tasks_by_id)
            if existing is not None:
                return existing, "existing_task", None
            tasks = scoped_refreshed_tasks
            tasks_by_id = refreshed_tasks_by_id

        return None, "planned_task", last_parent_id

    async def _list_tasks(self) -> list[Task]:
        result = await self.db.execute(
            select(Task)
            .where(Task.archived_at.is_(None))
            .options(selectinload(Task.runs))
            .order_by(Task.updated_at.desc())
        )
        return list(result.scalars())

    def _pick_existing_runnable_task(self, tasks: list[Task], tasks_by_id: dict[str, Task]) -> Task | None:
        candidates = [task for task in tasks if self._is_runnable_existing_task(task, tasks_by_id)]
        if not candidates:
            return None
        candidates.sort(key=self._existing_task_sort_key)
        return candidates[0]

    def _pick_parent_for_planning(self, tasks: list[Task], tasks_by_id: dict[str, Task]) -> Task | None:
        candidates = [task for task in tasks if self._is_plannable_parent_task(task, tasks_by_id)]
        if not candidates:
            return None
        candidates.sort(key=self._parent_task_sort_key)
        return candidates[0]

    def _pick_parents_for_planning(self, tasks: list[Task], tasks_by_id: dict[str, Task]) -> list[Task]:
        candidates = [task for task in tasks if self._is_plannable_parent_task(task, tasks_by_id)]
        candidates.sort(key=self._parent_task_sort_key)
        return candidates

    def _pick_latest_adoptable_run(self, tasks: list[Task], tasks_by_id: dict[str, Task]) -> tuple[Task, TaskRun] | None:
        candidates: list[tuple[Task, TaskRun]] = []
        for task in tasks:
            if task_has_unresolved_dependencies(task, tasks_by_id):
                continue
            latest_run = task.runs[-1] if task.runs else None
            if latest_run is None or latest_run.status != "passed" or latest_run.adopted_at is not None:
                continue
            if not self._can_auto_adopt(task, latest_run):
                continue
            candidates.append((task, latest_run))
        if not candidates:
            return None
        candidates.sort(key=lambda item: -item[1].created_at.timestamp())
        return candidates[0]

    def _pick_retry_candidate(self, tasks: list[Task], tasks_by_id: dict[str, Task]) -> tuple[Task, TaskRun] | None:
        candidates: list[tuple[Task, TaskRun]] = []
        for task in tasks:
            if task_has_unresolved_dependencies(task, tasks_by_id):
                continue
            latest_run = task.runs[-1] if task.runs else None
            if latest_run is None or not self._is_retry_candidate(task, latest_run):
                continue
            candidates.append((task, latest_run))
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                self._retry_candidate_signal_rank(item[0], item[1]),
                -item[1].created_at.timestamp(),
                -item[0].updated_at.timestamp(),
            )
        )
        return candidates[0]

    def _pick_retry_budget_exhausted_candidate(self, tasks: list[Task], tasks_by_id: dict[str, Task]) -> tuple[Task, TaskRun] | None:
        candidates: list[tuple[Task, TaskRun]] = []
        for task in tasks:
            if task_has_unresolved_dependencies(task, tasks_by_id):
                continue
            latest_run = task.runs[-1] if task.runs else None
            if latest_run is None:
                continue
            if latest_run.status != "failed":
                continue
            if self._is_terminal_task(task):
                continue
            if any(candidate.status in {"pending", "running"} for candidate in task.runs):
                continue
            if self._has_retry_budget(task):
                continue
            candidates.append((task, latest_run))
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                self._scope_rank(item[0]),
                self._priority_rank(item[0].priority),
                self._planning_reason_rank(item[0].metadata_ or {}),
                -item[1].created_at.timestamp(),
            )
        )
        return candidates[0]

    def _pick_continue_candidate(
        self,
        tasks: list[Task],
        *,
        create_plan_if_needed: bool,
    ) -> _ContinueCandidate | None:
        candidates: list[_ContinueCandidate] = []
        tasks_by_id = {task.id: task for task in tasks}

        adopt_candidate = self._pick_latest_adoptable_run(tasks, tasks_by_id)
        if adopt_candidate is not None:
            adopt_task, adopt_run = adopt_candidate
            candidates.append(
                _ContinueCandidate(
                    action="adopt",
                    task=adopt_task,
                    run=adopt_run,
                    rank=(
                        self._continue_action_rank("adopt"),
                        self._planning_reason_rank(adopt_task.metadata_ or {}),
                        self._scope_rank(adopt_task),
                        self._priority_rank(adopt_task.priority),
                        -adopt_run.created_at.timestamp(),
                    ),
                )
            )

        retry_candidate = self._pick_retry_candidate(tasks, tasks_by_id)
        if retry_candidate is not None:
            retry_task, retry_run = retry_candidate
            candidates.append(
                _ContinueCandidate(
                    action="retry",
                    task=retry_task,
                    run=retry_run,
                    rank=(
                        self._continue_action_rank("retry"),
                        self._retry_candidate_signal_rank(retry_task, retry_run),
                        self._priority_rank(retry_task.priority),
                        -retry_run.created_at.timestamp(),
                    ),
                )
            )

        exhausted_candidate = self._pick_retry_budget_exhausted_candidate(tasks, tasks_by_id)
        if exhausted_candidate is not None:
            exhausted_task, exhausted_run = exhausted_candidate
            candidates.append(
                _ContinueCandidate(
                    action="stop_retry_budget_exhausted",
                    task=exhausted_task,
                    run=exhausted_run,
                    rank=(
                        self._continue_action_rank("stop_retry_budget_exhausted"),
                        self._scope_rank(exhausted_task),
                        self._priority_rank(exhausted_task.priority),
                        self._planning_reason_rank(exhausted_task.metadata_ or {}),
                        -exhausted_run.created_at.timestamp(),
                    ),
                )
            )

        existing = self._pick_existing_runnable_task(tasks, tasks_by_id)
        if existing is not None:
            candidates.append(
                _ContinueCandidate(
                    action="dispatch_existing",
                    task=existing,
                    source="existing_task",
                    rank=(self._continue_action_rank("dispatch_existing"), *self._existing_task_sort_key(existing)),
                )
            )
        elif create_plan_if_needed:
            parent = self._pick_parent_for_planning(tasks, tasks_by_id)
            if parent is not None:
                candidates.append(
                    _ContinueCandidate(
                        action="plan_parent",
                        task=parent,
                        source="planned_task",
                        planned_from_task_id=parent.id,
                        rank=(self._continue_action_rank("plan_parent"), *self._parent_task_sort_key(parent)),
                    )
                )

        if not candidates:
            return None
        candidates.sort(key=lambda item: item.rank)
        return candidates[0]

    def _is_runnable_existing_task(self, task: Task, tasks_by_id: dict[str, Task]) -> bool:
        if self._is_terminal_task(task):
            return False
        if not self._recommended_prompt(task.metadata_ or {}):
            return False
        if any(run.status in {"pending", "running"} for run in task.runs):
            return False
        if task_has_unresolved_dependencies(task, tasks_by_id):
            return False
        latest_run = task.runs[-1] if task.runs else None
        if latest_run is not None and latest_run.status == "passed":
            return False
        if latest_run is not None and latest_run.status == "failed" and not self._has_retry_budget(task):
            return False
        return True

    def _is_plannable_parent_task(self, task: Task, tasks_by_id: dict[str, Task]) -> bool:
        if self._is_terminal_task(task):
            return False
        if (task.metadata_ or {}).get("parentTaskId"):
            return False
        if any(run.status in {"pending", "running"} for run in task.runs):
            return False
        if task_has_unresolved_dependencies(task, tasks_by_id):
            return False
        return task.status in {"open", "in_progress", "failed"}

    def _is_retry_candidate(self, task: Task, run: TaskRun) -> bool:
        if run.status != "failed":
            return False
        if self._is_terminal_task(task):
            return False
        if any(candidate.status in {"pending", "running"} for candidate in task.runs):
            return False
        return self._has_retry_budget(task)

    def _existing_task_sort_key(self, task: Task) -> tuple[int, int, int, int, int, float]:
        latest_run = task.runs[-1] if task.runs else None
        run_rank = 0 if latest_run is not None and latest_run.status == "failed" else 1
        return (
            run_rank,
            self._task_status_rank(task.status),
            self._planning_reason_rank(task.metadata_ or {}),
            self._scope_rank(task),
            self._priority_rank(task.priority),
            -task.updated_at.timestamp(),
        )

    def _parent_task_sort_key(self, task: Task) -> tuple[int, int, int, float]:
        latest_run = task.runs[-1] if task.runs else None
        return (
            self._parent_planning_signal_rank(task, latest_run),
            self._task_status_rank(task.status),
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

    def _continue_action_rank(self, action: str) -> int:
        if action == "adopt":
            return 0
        if action == "retry":
            return 1
        if action == "stop_retry_budget_exhausted":
            return 2
        if action == "dispatch_existing":
            return 3
        if action == "plan_parent":
            return 4
        return 4

    def _scope_rank(self, task: Task) -> int:
        return 0 if (task.metadata_ or {}).get("parentTaskId") else 1

    def _task_status_rank(self, status: str | None) -> int:
        normalized = (status or "").strip().lower()
        if normalized == "failed":
            return 0
        if normalized == "in_progress":
            return 1
        if normalized == "open":
            return 2
        return 3

    def _planning_reason_rank(self, metadata: dict[str, object]) -> int:
        reason = str(metadata.get("planningReason") or "").strip()
        if reason == "failed_run_follow_up":
            return 0
        if reason == "passed_run_not_adopted":
            return 1
        if reason == "review_compare_follow_up":
            return 2
        if reason == "task_next_step":
            return 3
        return 4

    def _retry_candidate_signal_rank(self, task: Task, run: TaskRun) -> int:
        latest_run = task.runs[-1] if task.runs else None
        latest_failed_rank = 0 if latest_run is not None and latest_run.id == run.id else 1
        return (
            latest_failed_rank * 100
            + self._task_status_rank(task.status) * 10
            + self._planning_reason_rank(task.metadata_ or {})
        )

    def _parent_planning_signal_rank(self, task: Task, latest_run: TaskRun | None) -> int:
        if latest_run is not None and latest_run.status == "failed":
            return 0
        if latest_run is not None and latest_run.status == "passed" and latest_run.adopted_at is None:
            return 1
        if task.status == "failed":
            return 2
        return 3

    def _scope_root_task_id(self, tasks: list[Task], task_id: str | None) -> str | None:
        if task_id is None:
            return None
        task_by_id = {task.id: task for task in tasks}
        task = task_by_id.get(task_id)
        if task is None:
            return task_id
        parent_id = (task.metadata_ or {}).get("parentTaskId")
        if isinstance(parent_id, str) and parent_id.strip():
            return parent_id.strip()
        return task.id

    def _scope_root_task(self, tasks: list[Task], task_id: str | None) -> Task | None:
        if task_id is None:
            return None
        root_id = self._scope_root_task_id(tasks, task_id)
        if root_id is None:
            return None
        return next((task for task in tasks if task.id == root_id), None)

    def _scope_tasks(self, tasks: list[Task], task_id: str | None) -> list[Task]:
        if task_id is None:
            return tasks
        root_id = self._scope_root_task_id(tasks, task_id)
        if root_id is None:
            return []
        return [
            task
            for task in tasks
            if task.id == root_id or (task.metadata_ or {}).get("parentTaskId") == root_id
        ]

    def _consecutive_failed_runs(self, task: Task) -> int:
        count = 0
        for run in reversed(task.runs):
            if run.status != "failed":
                break
            count += 1
        return count

    def _has_retry_budget(self, task: Task) -> bool:
        return self._consecutive_failed_runs(task) < self.AUTO_RETRY_FAILURE_LIMIT

    def _can_auto_adopt(self, task: Task, run: TaskRun) -> bool:
        if task.repo_path is None or run.worktree_path is None:
            return False
        repo_path = Path(task.repo_path)
        worktree_path = Path(run.worktree_path)
        return repo_path.exists() and worktree_path.exists()


def task_has_unresolved_dependencies(task: Task, tasks_by_id: dict[str, Task]) -> bool:
    return not build_task_dependency_state(task, tasks_by_id).ready
