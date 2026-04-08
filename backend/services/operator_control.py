from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Task, TaskRun, now
from services.github_issue_monitors import list_issue_monitors
from services.run_engine import RunEngine
from services.task_autodrive import (
    AUTO_DRIVE_ENABLED_KEY,
    GlobalAutoDriveControlResult,
    GlobalAutoDriveService,
    TaskAutoDriveService,
)
from services.task_dependencies import build_task_dependency_state
from services.task_dispatcher import TaskDispatcherService


OperatorActionKey = Literal[
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

OperatorTone = Literal["green", "amber", "red", "gray"]

ISSUE_MONITOR_ERROR_STATUSES = {"failed", "source-error"}


@dataclass(frozen=True)
class OperatorActionDescriptor:
    key: OperatorActionKey
    label: str
    description: str
    tone: str
    task_id: str | None = None
    run_id: str | None = None
    disabled: bool = False
    disabled_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "tone": self.tone,
            "taskId": self.task_id,
            "runId": self.run_id,
            "disabled": self.disabled,
            "disabledReason": self.disabled_reason,
        }


@dataclass(frozen=True)
class OperatorAttentionItem:
    kind: str
    title: str
    summary: str
    tone: OperatorTone
    task_id: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "tone": self.tone,
            "taskId": self.task_id,
            "runId": self.run_id,
        }


@dataclass(frozen=True)
class OperatorIssueMonitor:
    repo: str
    repo_path: str | None
    running: bool
    status: str
    summary: str
    last_checked_at: str | None
    issue_count: int | None
    changed_issue_count: int | None
    task_ids: list[str] = field(default_factory=list)
    attention: bool = False
    tone: OperatorTone = "gray"

    def to_dict(self) -> dict[str, object]:
        return {
            "repo": self.repo,
            "repoPath": self.repo_path,
            "running": self.running,
            "status": self.status,
            "summary": self.summary,
            "lastCheckedAt": self.last_checked_at,
            "issueCount": self.issue_count,
            "changedIssueCount": self.changed_issue_count,
            "taskIds": list(self.task_ids),
            "attention": self.attention,
            "tone": self.tone,
        }


@dataclass(frozen=True)
class OperatorStats:
    total_task_count: int
    runnable_task_count: int
    blocked_task_count: int
    failed_task_count: int
    pending_run_count: int
    running_run_count: int
    passed_run_awaiting_adopt_count: int
    scope_autodrive_enabled_count: int
    issue_monitor_count: int
    issue_monitor_running_count: int
    issue_monitor_attention_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "totalTaskCount": self.total_task_count,
            "runnableTaskCount": self.runnable_task_count,
            "blockedTaskCount": self.blocked_task_count,
            "failedTaskCount": self.failed_task_count,
            "pendingRunCount": self.pending_run_count,
            "runningRunCount": self.running_run_count,
            "passedRunAwaitingAdoptCount": self.passed_run_awaiting_adopt_count,
            "scopeAutodriveEnabledCount": self.scope_autodrive_enabled_count,
            "issueMonitorCount": self.issue_monitor_count,
            "issueMonitorRunningCount": self.issue_monitor_running_count,
            "issueMonitorAttentionCount": self.issue_monitor_attention_count,
        }


@dataclass(frozen=True)
class OperatorFocus:
    task: dict[str, object] | None
    scope_task: dict[str, object] | None
    active_run: dict[str, object] | None
    summary: str | None
    reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task,
            "scopeTask": self.scope_task,
            "activeRun": self.active_run,
            "summary": self.summary,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OperatorControlPlane:
    generated_at: str
    system_status: str
    system_summary: str
    global_autodrive: GlobalAutoDriveControlResult
    stats: OperatorStats
    focus: OperatorFocus
    issue_monitors: list[OperatorIssueMonitor] = field(default_factory=list)
    actions: list[OperatorActionDescriptor] = field(default_factory=list)
    attention: list[OperatorAttentionItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "generatedAt": self.generated_at,
            "systemStatus": self.system_status,
            "systemSummary": self.system_summary,
            "globalAutoDrive": self.global_autodrive.to_dict(),
            "stats": self.stats.to_dict(),
            "focus": self.focus.to_dict(),
            "issueMonitors": [item.to_dict() for item in self.issue_monitors],
            "actions": [item.to_dict() for item in self.actions],
            "attention": [item.to_dict() for item in self.attention],
            "recentEvents": list(self.global_autodrive.recent_events),
        }


@dataclass(frozen=True)
class OperatorActionResult:
    action: OperatorActionKey
    summary: str
    control_plane: OperatorControlPlane
    task_id: str | None = None
    run_id: str | None = None
    continue_decision: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": True,
            "action": self.action,
            "summary": self.summary,
            "taskId": self.task_id,
            "runId": self.run_id,
            "continueDecision": self.continue_decision,
            "controlPlane": self.control_plane.to_dict(),
        }


class OperatorControlService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_control_plane(self, *, task_id: str | None = None) -> OperatorControlPlane:
        tasks = await self._list_tasks()
        tasks_by_id = {task.id: task for task in tasks}
        dependency_states = {task.id: build_task_dependency_state(task, tasks_by_id) for task in tasks}
        dispatcher = TaskDispatcherService(self.db)
        global_status = await GlobalAutoDriveService(self.db).get_status()
        issue_monitors = self._build_issue_monitors()
        issue_monitor_attention = next((item for item in issue_monitors if item.attention), None)

        selected_task = tasks_by_id.get(task_id) if task_id else None
        focus_task = selected_task
        if focus_task is None and global_status.current_task_id:
            focus_task = tasks_by_id.get(global_status.current_task_id)

        active_run, active_run_task = self._latest_active_run(tasks, tasks_by_id)
        if focus_task is None and active_run_task is not None:
            focus_task = active_run_task

        adopt_candidate = dispatcher._pick_latest_adoptable_run(tasks, tasks_by_id)
        retry_candidate = dispatcher._pick_retry_candidate(tasks, tasks_by_id)
        exhausted_candidate = dispatcher._pick_retry_budget_exhausted_candidate(tasks, tasks_by_id)
        blocked_tasks = [task for task in tasks if not dependency_states[task.id].ready]
        blocked_tasks.sort(key=lambda item: self._task_sort_key(item))
        blocked_candidate = blocked_tasks[0] if blocked_tasks else None
        runnable_candidate = dispatcher._pick_existing_runnable_task(tasks, tasks_by_id)

        if focus_task is None:
            if adopt_candidate is not None:
                focus_task = adopt_candidate[0]
            elif retry_candidate is not None:
                focus_task = retry_candidate[0]
            elif blocked_candidate is not None:
                focus_task = blocked_candidate
            elif runnable_candidate is not None:
                focus_task = runnable_candidate

        scope_task = self._scope_root_task(focus_task, tasks_by_id)
        if scope_task is None and global_status.current_scope_task_id:
            scope_task = tasks_by_id.get(global_status.current_scope_task_id)
        if scope_task is None and active_run_task is not None:
            scope_task = self._scope_root_task(active_run_task, tasks_by_id)

        focus_summary, focus_reason = self._build_focus_summary(
            global_status=global_status,
            focus_task=focus_task,
            scope_task=scope_task,
            active_run=active_run,
            active_run_task=active_run_task,
            adopt_candidate=adopt_candidate,
            retry_candidate=retry_candidate,
            exhausted_candidate=exhausted_candidate,
            blocked_candidate=blocked_candidate,
            dependency_states=dependency_states,
            runnable_candidate=runnable_candidate,
        )
        system_status, system_summary = self._build_system_status(
            global_status=global_status,
            issue_monitor_attention=issue_monitor_attention,
            active_run=active_run,
            adopt_candidate=adopt_candidate,
            retry_candidate=retry_candidate,
            exhausted_candidate=exhausted_candidate,
            blocked_tasks=blocked_tasks,
            runnable_candidate=runnable_candidate,
            focus_summary=focus_summary,
        )

        stats = OperatorStats(
            total_task_count=len(tasks),
            runnable_task_count=sum(1 for task in tasks if dispatcher._is_runnable_existing_task(task, tasks_by_id)),
            blocked_task_count=len(blocked_tasks),
            failed_task_count=sum(1 for task in tasks if self._latest_run(task) is not None and self._latest_run(task).status == "failed"),
            pending_run_count=sum(1 for task in tasks for run in task.runs if run.status == "pending"),
            running_run_count=sum(1 for task in tasks for run in task.runs if run.status == "running"),
            passed_run_awaiting_adopt_count=sum(
                1
                for task in tasks
                if self._latest_run(task) is not None
                and self._latest_run(task).status == "passed"
                and self._latest_run(task).adopted_at is None
            ),
            scope_autodrive_enabled_count=sum(
                1
                for task in tasks
                if not self._parent_task_id(task) and bool((task.metadata_ or {}).get(AUTO_DRIVE_ENABLED_KEY))
            ),
            issue_monitor_count=len(issue_monitors),
            issue_monitor_running_count=sum(1 for item in issue_monitors if item.running),
            issue_monitor_attention_count=sum(1 for item in issue_monitors if item.attention),
        )

        focus = OperatorFocus(
            task=self._serialize_task(focus_task, dependency_states) if focus_task is not None else None,
            scope_task=self._serialize_task(scope_task, dependency_states) if scope_task is not None else None,
            active_run=active_run.to_dict() if active_run is not None else None,
            summary=focus_summary,
            reason=focus_reason,
        )

        actions = self._build_actions(
            dispatcher=dispatcher,
            global_status=global_status,
            focus_task=focus_task,
            scope_task=scope_task,
            active_run=active_run,
            adopt_candidate=adopt_candidate,
            retry_candidate=retry_candidate,
            dependency_states=dependency_states,
            tasks=tasks,
            tasks_by_id=tasks_by_id,
        )
        attention = self._build_attention(
            global_status=global_status,
            issue_monitors=issue_monitors,
            active_run=active_run,
            active_run_task=active_run_task,
            adopt_candidate=adopt_candidate,
            retry_candidate=retry_candidate,
            exhausted_candidate=exhausted_candidate,
            blocked_candidate=blocked_candidate,
            dependency_states=dependency_states,
        )

        return OperatorControlPlane(
            generated_at=now().isoformat(),
            system_status=system_status,
            system_summary=system_summary,
            global_autodrive=global_status,
            stats=stats,
            focus=focus,
            issue_monitors=issue_monitors,
            actions=actions,
            attention=attention,
        )

    async def perform_action(
        self,
        *,
        action: OperatorActionKey,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> OperatorActionResult:
        selected_task_id = task_id
        affected_run_id = run_id
        continue_decision: dict[str, object] | None = None

        if action == "start_global_autodrive":
            result = await GlobalAutoDriveService(self.db).start()
            summary = result.summary
        elif action == "stop_global_autodrive":
            result = await GlobalAutoDriveService(self.db).stop()
            summary = result.summary
        elif action == "restart_global_autodrive":
            service = GlobalAutoDriveService(self.db)
            status = await service.get_status()
            if status.enabled:
                await service.stop()
            await service.start()
            summary = "已重启全局无人值守 supervisor。"
        elif action == "dispatch_next":
            dispatched = await TaskDispatcherService(self.db).dispatch_next(create_plan_if_needed=True)
            if dispatched is None:
                raise HTTPException(status_code=409, detail="当前没有可重新触发的任务。")
            selected_task_id = dispatched.task.id
            affected_run_id = dispatched.run.id
            summary = (
                f"已先拆后跑：{dispatched.task.title}"
                if dispatched.source == "planned_task"
                else f"已接手下一张任务：{dispatched.task.title}"
            )
        elif action == "continue_task_family":
            target_task_id = self._require_task_id(task_id)
            result = await TaskDispatcherService(self.db).continue_task(
                task_id=target_task_id,
                create_plan_if_needed=True,
            )
            selected_task_id = result.task.id if result.task is not None else result.scope_task_id or target_task_id
            affected_run_id = result.run.id if result.run is not None else None
            summary = result.summary
            continue_decision = result.to_dict()
        elif action == "start_task_autodrive":
            target_task_id = self._require_task_id(task_id)
            result = await TaskAutoDriveService(self.db).start(target_task_id)
            if result is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            selected_task_id = result.scope_task_id
            summary = result.summary
        elif action == "stop_task_autodrive":
            target_task_id = self._require_task_id(task_id)
            result = await TaskAutoDriveService(self.db).stop(target_task_id)
            if result is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            selected_task_id = result.scope_task_id
            summary = result.summary
        elif action == "adopt_run":
            target_run_id = self._require_run_id(run_id)
            result = await RunEngine(self.db).adopt_run(target_run_id)
            if not result.get("ok"):
                raise HTTPException(status_code=409, detail=str(result.get("error") or "采纳失败"))
            task_run = await self.db.get(TaskRun, target_run_id)
            selected_task_id = task_run.task_id if task_run is not None else selected_task_id
            affected_run_id = target_run_id
            summary = f"已采纳 run {target_run_id}。"
        elif action == "retry_run":
            target_run_id = self._require_run_id(run_id)
            task_run = await self.db.get(TaskRun, target_run_id)
            if task_run is None:
                raise HTTPException(status_code=404, detail="执行记录不存在")
            task = await self.db.get(Task, task_run.task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            dependency_state = build_task_dependency_state(task, {item.id: item for item in await self._list_tasks()})
            if not dependency_state.ready:
                raise HTTPException(status_code=409, detail=dependency_state.summary or "当前任务仍被依赖阻塞")
            retried = await RunEngine(self.db).retry_run(target_run_id)
            if retried is None:
                raise HTTPException(status_code=404, detail="执行记录不存在")
            selected_task_id = retried.task_id
            affected_run_id = retried.id
            summary = f"已重新触发 run {target_run_id}。"
        elif action == "cancel_run":
            target_run_id = self._require_run_id(run_id)
            cancelled = await RunEngine(self.db).cancel_run(target_run_id)
            if cancelled is None:
                raise HTTPException(status_code=404, detail="执行记录不存在")
            if cancelled.status not in {"pending", "running", "cancelled"}:
                raise HTTPException(status_code=409, detail="当前 run 不在执行中，无法打断")
            selected_task_id = cancelled.task_id
            affected_run_id = cancelled.id
            summary = f"已打断 run {target_run_id}。"
        else:
            raise HTTPException(status_code=400, detail="未知 operator 动作")

        control_plane = await self.get_control_plane(task_id=selected_task_id)
        return OperatorActionResult(
            action=action,
            summary=summary,
            control_plane=control_plane,
            task_id=selected_task_id,
            run_id=affected_run_id,
            continue_decision=continue_decision,
        )

    async def _list_tasks(self) -> list[Task]:
        result = await self.db.execute(
            select(Task)
            .where(Task.archived_at.is_(None))
            .options(selectinload(Task.runs))
            .order_by(Task.updated_at.desc())
        )
        return list(result.scalars())

    def _build_actions(
        self,
        *,
        dispatcher: TaskDispatcherService,
        global_status: GlobalAutoDriveControlResult,
        focus_task: Task | None,
        scope_task: Task | None,
        active_run: TaskRun | None,
        adopt_candidate: tuple[Task, TaskRun] | None,
        retry_candidate: tuple[Task, TaskRun] | None,
        dependency_states: dict[str, object],
        tasks: list[Task],
        tasks_by_id: dict[str, Task],
    ) -> list[OperatorActionDescriptor]:
        actions: list[OperatorActionDescriptor] = []

        if global_status.enabled:
            actions.append(
                OperatorActionDescriptor(
                    key="stop_global_autodrive",
                    label="停止全局无人值守",
                    description="停止跨 task family 的自动接活与自动继续。",
                    tone="gray",
                )
            )
            actions.append(
                OperatorActionDescriptor(
                    key="restart_global_autodrive",
                    label="重启全局 supervisor",
                    description="重新拉起全局无人值守 supervisor，用于异常恢复或 lease 重新接管。",
                    tone="amber",
                )
            )
        else:
            actions.append(
                OperatorActionDescriptor(
                    key="start_global_autodrive",
                    label="开启全局无人值守",
                    description="让 KAM 持续跨 task family 接活并闭环推进。",
                    tone="green",
                )
            )

        has_dispatch_candidate = dispatcher._pick_existing_runnable_task(tasks, tasks_by_id) is not None or bool(
            dispatcher._pick_parents_for_planning(tasks, tasks_by_id)
        )
        actions.append(
            OperatorActionDescriptor(
                key="dispatch_next",
                label="让 KAM 接下一张",
                description="从当前任务池里挑下一张高价值任务，必要时先拆再跑。",
                tone="green",
                disabled=not has_dispatch_candidate,
                disabled_reason=None if has_dispatch_candidate else "当前没有可接手的任务。",
            )
        )

        if scope_task is not None:
            scope_state = dependency_states[scope_task.id]
            scope_has_active_run = any(run.status in {"pending", "running"} for run in scope_task.runs)
            continue_disabled_reason = None
            if scope_task.status in {"archived", "done", "verified", "blocked"}:
                continue_disabled_reason = "当前任务族已经收口。"
            elif not scope_state.ready:
                continue_disabled_reason = scope_state.summary or "当前任务族仍被依赖阻塞。"
            elif scope_has_active_run:
                continue_disabled_reason = "当前任务族里还有 run 在执行。"

            actions.append(
                OperatorActionDescriptor(
                    key="continue_task_family",
                    label="继续推进当前任务",
                    description="围绕当前 task family 重新判断 adopt / retry / plan / dispatch。",
                    tone="green",
                    task_id=scope_task.id,
                    disabled=continue_disabled_reason is not None,
                    disabled_reason=continue_disabled_reason,
                )
            )

            scope_enabled = bool((scope_task.metadata_ or {}).get(AUTO_DRIVE_ENABLED_KEY))
            scope_autodrive_disabled_reason = None
            if scope_task.status in {"archived", "done", "verified", "blocked"}:
                scope_autodrive_disabled_reason = "当前任务族已经收口。"
            elif not scope_state.ready and not scope_enabled:
                scope_autodrive_disabled_reason = scope_state.summary or "当前任务族仍被依赖阻塞。"

            actions.append(
                OperatorActionDescriptor(
                    key="stop_task_autodrive" if scope_enabled else "start_task_autodrive",
                    label="停止无人值守" if scope_enabled else "进入无人值守",
                    description="只围绕当前 task family 持续自动推进，不影响其他 family。",
                    tone="gray" if scope_enabled else "amber",
                    task_id=scope_task.id,
                    disabled=scope_autodrive_disabled_reason is not None,
                    disabled_reason=scope_autodrive_disabled_reason,
                )
            )

        if active_run is not None:
            actions.append(
                OperatorActionDescriptor(
                    key="cancel_run",
                    label="打断当前 Run",
                    description="终止当前正在执行的 agent run，并把状态标记为 cancelled。",
                    tone="red",
                    task_id=active_run.task_id,
                    run_id=active_run.id,
                )
            )

        if adopt_candidate is not None:
            adopt_task, adopt_run = adopt_candidate
            actions.append(
                OperatorActionDescriptor(
                    key="adopt_run",
                    label="采纳最近结果",
                    description="把最近通过且可采纳的 run 收口回主工作区。",
                    tone="green",
                    task_id=adopt_task.id,
                    run_id=adopt_run.id,
                )
            )

        if retry_candidate is not None:
            retry_task, failed_run = retry_candidate
            actions.append(
                OperatorActionDescriptor(
                    key="retry_run",
                    label="重试最近失败 Run",
                    description="重新触发最近失败且仍有预算的 run。",
                    tone="amber",
                    task_id=retry_task.id,
                    run_id=failed_run.id,
                )
            )

        unique: list[OperatorActionDescriptor] = []
        seen: set[tuple[object, ...]] = set()
        for action in actions:
            signature = (action.key, action.task_id, action.run_id)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(action)
        return unique

    def _build_attention(
        self,
        *,
        global_status: GlobalAutoDriveControlResult,
        issue_monitors: list[OperatorIssueMonitor],
        active_run: TaskRun | None,
        active_run_task: Task | None,
        adopt_candidate: tuple[Task, TaskRun] | None,
        retry_candidate: tuple[Task, TaskRun] | None,
        exhausted_candidate: tuple[Task, TaskRun] | None,
        blocked_candidate: Task | None,
        dependency_states: dict[str, object],
    ) -> list[OperatorAttentionItem]:
        items: list[OperatorAttentionItem] = []
        if global_status.status == "error":
            items.append(
                OperatorAttentionItem(
                    kind="global_error",
                    title="全局无人值守异常",
                    summary=global_status.error or global_status.summary,
                    tone="red",
                )
            )
        for monitor in issue_monitors:
            if not monitor.attention:
                continue
            items.append(
                OperatorAttentionItem(
                    kind=f"issue_monitor_{monitor.status}",
                    title=f"GitHub Issue monitor · {monitor.repo}",
                    summary=monitor.summary,
                    tone=monitor.tone,
                )
            )
        if active_run is not None:
            task_title = active_run_task.title if active_run_task is not None else active_run.task_id
            items.append(
                OperatorAttentionItem(
                    kind="active_run",
                    title=f"Run {active_run.id} 正在执行",
                    summary=f"{task_title} 正在由 {active_run.agent} 执行；需要打断时可取消当前 run。",
                    tone="amber",
                    task_id=active_run.task_id,
                    run_id=active_run.id,
                )
            )
        if adopt_candidate is not None:
            adopt_task, adopt_run = adopt_candidate
            items.append(
                OperatorAttentionItem(
                    kind="awaiting_adopt",
                    title=f"Run {adopt_run.id} 等待采纳",
                    summary=f"{adopt_task.title} 最近一次执行已通过，但还没有采纳。",
                    tone="green",
                    task_id=adopt_task.id,
                    run_id=adopt_run.id,
                )
            )
        if exhausted_candidate is not None:
            exhausted_task, exhausted_run = exhausted_candidate
            items.append(
                OperatorAttentionItem(
                    kind="retry_budget_exhausted",
                    title=f"{exhausted_task.title} 已暂停",
                    summary=f"最近失败 run {exhausted_run.id} 已达到自动重试上限，需要人工判断。",
                    tone="red",
                    task_id=exhausted_task.id,
                    run_id=exhausted_run.id,
                )
            )
        elif retry_candidate is not None:
            retry_task, failed_run = retry_candidate
            items.append(
                OperatorAttentionItem(
                    kind="failed_run",
                    title=f"{retry_task.title} 最近失败",
                    summary=f"最近失败 run {failed_run.id} 仍可重试。",
                    tone="amber",
                    task_id=retry_task.id,
                    run_id=failed_run.id,
                )
            )
        if blocked_candidate is not None:
            blocked_state = dependency_states[blocked_candidate.id]
            items.append(
                OperatorAttentionItem(
                    kind="blocked_task",
                    title=f"{blocked_candidate.title} 被阻塞",
                    summary=blocked_state.summary or "存在未完成的上游依赖。",
                    tone="gray",
                    task_id=blocked_candidate.id,
                )
            )
        return items[:4]

    def _build_system_status(
        self,
        *,
        global_status: GlobalAutoDriveControlResult,
        issue_monitor_attention: OperatorIssueMonitor | None,
        active_run: TaskRun | None,
        adopt_candidate: tuple[Task, TaskRun] | None,
        retry_candidate: tuple[Task, TaskRun] | None,
        exhausted_candidate: tuple[Task, TaskRun] | None,
        blocked_tasks: list[Task],
        runnable_candidate: Task | None,
        focus_summary: str | None,
    ) -> tuple[str, str]:
        if active_run is not None:
            return "running", focus_summary or f"当前 run {active_run.id} 正在执行。"
        if global_status.status == "error":
            return "attention", global_status.error or global_status.summary
        if adopt_candidate is not None:
            return "attention", focus_summary or "有通过的 run 等待采纳。"
        if exhausted_candidate is not None:
            return "attention", focus_summary or "有失败任务达到自动重试上限，需要人工介入。"
        if retry_candidate is not None:
            return "attention", focus_summary or "有失败任务等待重新触发。"
        if blocked_tasks:
            return "attention", focus_summary or f"当前有 {len(blocked_tasks)} 张任务被依赖阻塞。"
        if issue_monitor_attention is not None:
            return "attention", issue_monitor_attention.summary
        if runnable_candidate is not None:
            return "ready", focus_summary or "当前有任务可继续推进。"
        if global_status.enabled:
            return global_status.status, global_status.summary
        return "idle", focus_summary or "当前无人值守未开启，也没有需要立刻处理的动作。"

    def _build_focus_summary(
        self,
        *,
        global_status: GlobalAutoDriveControlResult,
        focus_task: Task | None,
        scope_task: Task | None,
        active_run: TaskRun | None,
        active_run_task: Task | None,
        adopt_candidate: tuple[Task, TaskRun] | None,
        retry_candidate: tuple[Task, TaskRun] | None,
        exhausted_candidate: tuple[Task, TaskRun] | None,
        blocked_candidate: Task | None,
        dependency_states: dict[str, object],
        runnable_candidate: Task | None,
    ) -> tuple[str | None, str | None]:
        if active_run is not None:
            task_title = active_run_task.title if active_run_task is not None else active_run.task_id
            return f"{task_title} 正在执行中；需要打断时可取消当前 run。", "active_run"
        if adopt_candidate is not None:
            adopt_task, adopt_run = adopt_candidate
            return f"{adopt_task.title} 的通过结果 {adopt_run.id} 还没有采纳。", "awaiting_adopt"
        if exhausted_candidate is not None:
            exhausted_task, exhausted_run = exhausted_candidate
            return f"{exhausted_task.title} 的失败 run {exhausted_run.id} 已达到自动重试上限。", "retry_budget_exhausted"
        if retry_candidate is not None:
            retry_task, failed_run = retry_candidate
            return f"{retry_task.title} 的失败 run {failed_run.id} 可重新触发。", "retry_ready"
        if blocked_candidate is not None:
            blocked_state = dependency_states[blocked_candidate.id]
            return blocked_state.summary or "当前存在被依赖阻塞的任务。", "blocked"
        if runnable_candidate is not None:
            return f"{runnable_candidate.title} 当前可直接继续。", "runnable"
        if scope_task is not None and focus_task is not None:
            return f"当前焦点任务是 {focus_task.title}，所属任务族为 {scope_task.title}。", "focus_task"
        if focus_task is not None:
            return f"当前焦点任务是 {focus_task.title}。", "focus_task"
        return global_status.summary, "global_summary"

    def _latest_active_run(self, tasks: list[Task], tasks_by_id: dict[str, Task]) -> tuple[TaskRun | None, Task | None]:
        candidates = [
            run
            for task in tasks
            for run in task.runs
            if run.status in {"pending", "running"}
        ]
        if not candidates:
            return None, None
        candidates.sort(key=lambda item: item.created_at.timestamp(), reverse=True)
        run = candidates[0]
        return run, tasks_by_id.get(run.task_id)

    def _scope_root_task(self, task: Task | None, tasks_by_id: dict[str, Task]) -> Task | None:
        if task is None:
            return None
        parent_id = self._parent_task_id(task)
        if parent_id is None:
            return task
        return tasks_by_id.get(parent_id) or task

    def _parent_task_id(self, task: Task) -> str | None:
        value = (task.metadata_ or {}).get("parentTaskId")
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _latest_run(self, task: Task) -> TaskRun | None:
        return task.runs[-1] if task.runs else None

    def _task_sort_key(self, task: Task) -> tuple[int, int, float]:
        dispatcher = TaskDispatcherService(self.db)
        return (
            dispatcher._priority_rank(task.priority),
            dispatcher._task_status_rank(task.status),
            -task.updated_at.timestamp(),
        )

    def _serialize_task(self, task: Task | None, dependency_states: dict[str, object]) -> dict[str, object] | None:
        if task is None:
            return None
        dependency_state = dependency_states.get(task.id)
        return task.to_dict(dependency_state=dependency_state.to_dict() if dependency_state is not None else None)

    def _build_issue_monitors(self) -> list[OperatorIssueMonitor]:
        monitors: list[OperatorIssueMonitor] = []
        for item in list_issue_monitors():
            if not isinstance(item, dict):
                continue
            repo = str(item.get("repo") or "").strip()
            if not repo:
                continue
            status = str(item.get("status") or "idle").strip() or "idle"
            running = item.get("running") is True
            attention = status in ISSUE_MONITOR_ERROR_STATUSES or not running
            tone: OperatorTone
            if status in ISSUE_MONITOR_ERROR_STATUSES:
                tone = "red"
            elif not running:
                tone = "amber"
            elif status == "enqueued":
                tone = "green"
            else:
                tone = "gray"
            task_ids = item.get("taskIds") if isinstance(item.get("taskIds"), list) else []
            monitors.append(
                OperatorIssueMonitor(
                    repo=repo,
                    repo_path=str(item.get("repoPath")).strip() if isinstance(item.get("repoPath"), str) and str(item.get("repoPath")).strip() else None,
                    running=running,
                    status=status,
                    summary=str(item.get("summary") or "").strip() or "监控状态未知。",
                    last_checked_at=str(item.get("lastCheckedAt")).strip() if isinstance(item.get("lastCheckedAt"), str) and str(item.get("lastCheckedAt")).strip() else None,
                    issue_count=item.get("issueCount") if isinstance(item.get("issueCount"), int) else None,
                    changed_issue_count=item.get("changedIssueCount") if isinstance(item.get("changedIssueCount"), int) else None,
                    task_ids=[str(value).strip() for value in task_ids if isinstance(value, str) and str(value).strip()],
                    attention=attention,
                    tone=tone,
                )
            )
        return monitors

    def _require_task_id(self, task_id: str | None) -> str:
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()
        raise HTTPException(status_code=422, detail="缺少 taskId")

    def _require_run_id(self, run_id: str | None) -> str:
        if isinstance(run_id, str) and run_id.strip():
            return run_id.strip()
        raise HTTPException(status_code=422, detail="缺少 runId")
