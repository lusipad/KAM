from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import ReviewCompare, Task, TaskRun, now


@dataclass
class PlannedTaskSuggestion:
    title: str
    description: str
    priority: str
    labels: list[str]
    metadata: dict[str, object]
    rationale: str

    def signature(self) -> tuple[str, str, str]:
        return (
            self.metadata.get("planningReason", ""),
            self.metadata.get("sourceRunId", ""),
            self.metadata.get("sourceCompareId", ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "labels": self.labels,
            "metadata": self.metadata,
            "rationale": self.rationale,
        }


class TaskPlannerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def plan_follow_ups(
        self,
        task_id: str,
        *,
        limit: int = 3,
        create_tasks: bool = True,
    ) -> dict[str, object] | None:
        task, suggestions, created_tasks = await self.plan(
            task_id,
            limit=limit,
            create_tasks=create_tasks,
        )
        if task is None:
            return None
        return {
            "taskId": task.id,
            "suggestions": [item.to_dict() for item in suggestions],
            "tasks": [item.to_dict() for item in created_tasks],
        }

    async def plan(
        self,
        task_id: str,
        *,
        limit: int = 3,
        create_tasks: bool = True,
    ) -> tuple[Task | None, list[PlannedTaskSuggestion], list[Task]]:
        task = await self._load_task(task_id)
        if task is None:
            return None, [], []

        existing_signatures = {
            self._metadata_signature(item.metadata_ or {})
            for item in await self._list_existing_follow_ups(task.id)
        }
        suggestions = self._build_suggestions(task, existing_signatures, max(1, limit))

        if not create_tasks or not suggestions:
            return task, suggestions, []

        created_tasks: list[Task] = []
        for suggestion in suggestions:
            created = Task(
                title=suggestion.title,
                description=suggestion.description,
                repo_path=task.repo_path,
                status="open",
                priority=suggestion.priority,
                labels=suggestion.labels,
                metadata_=suggestion.metadata,
            )
            self.db.add(created)
            created_tasks.append(created)

        task.updated_at = now()
        await self.db.commit()
        for created in created_tasks:
            await self.db.refresh(created)
        return task, suggestions, created_tasks

    async def _load_task(self, task_id: str) -> Task | None:
        stmt = (
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.refs),
                selectinload(Task.snapshots),
                selectinload(Task.review_compares),
                selectinload(Task.runs),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _list_existing_follow_ups(self, parent_task_id: str) -> list[Task]:
        result = await self.db.execute(select(Task).order_by(Task.created_at.asc()))
        tasks = list(result.scalars())
        return [
            task
            for task in tasks
            if (task.metadata_ or {}).get("parentTaskId") == parent_task_id
        ]

    def _build_suggestions(
        self,
        task: Task,
        existing_signatures: set[tuple[str, str, str]],
        limit: int,
    ) -> list[PlannedTaskSuggestion]:
        suggestions: list[PlannedTaskSuggestion] = []

        latest_failed_run = next((run for run in reversed(task.runs) if run.status == "failed"), None)
        if latest_failed_run is not None:
            suggestions.append(self._build_failed_run_follow_up(task, latest_failed_run))

        latest_unadopted_run = next(
            (run for run in reversed(task.runs) if run.status == "passed" and run.adopted_at is None),
            None,
        )
        if latest_unadopted_run is not None:
            suggestions.append(self._build_adopt_follow_up(task, latest_unadopted_run))

        latest_compare = task.review_compares[-1] if task.review_compares else None
        if latest_compare is not None:
            suggestions.append(self._build_compare_follow_up(task, latest_compare))

        if not suggestions:
            suggestions.append(self._build_generic_follow_up(task))

        unique_suggestions: list[PlannedTaskSuggestion] = []
        seen_signatures = set(existing_signatures)
        for suggestion in suggestions:
            signature = suggestion.signature()
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique_suggestions.append(suggestion)
            if len(unique_suggestions) >= limit:
                break

        return unique_suggestions

    def _build_failed_run_follow_up(self, task: Task, run: TaskRun) -> PlannedTaskSuggestion:
        summary = self._short_text(run.result_summary or run.task, 80)
        return PlannedTaskSuggestion(
            title=f"修复失败 run：{self._short_text(run.task, 40)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    f"失败 run：{run.agent} · {summary}",
                    "先消除失败原因，再决定是否继续当前主任务。",
                ]
            ),
            priority="high",
            labels=self._merge_labels(task.labels, "follow-up", "failure"),
            metadata=self._build_metadata(
                task,
                planning_reason="failed_run_follow_up",
                source_kind="run",
                source_run_id=run.id,
            ),
            rationale="最近一轮 run 失败，需要先拆出修复工作保持主链路可推进。",
        )

    def _build_adopt_follow_up(self, task: Task, run: TaskRun) -> PlannedTaskSuggestion:
        summary = self._short_text(run.result_summary or run.task, 120)
        changed_files = ", ".join((run.changed_files or [])[:3]) or "无文件列表"
        return PlannedTaskSuggestion(
            title=f"采纳并验证：{self._short_text(summary, 42)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    f"待采纳 run：{run.agent} · {summary}",
                    f"涉及文件：{changed_files}",
                    "采纳前先复核 artifacts、patch 和验证结果，再决定是否合入主线。",
                ]
            ),
            priority="high" if task.priority == "high" else "medium",
            labels=self._merge_labels(task.labels, "follow-up", "adopt"),
            metadata=self._build_metadata(
                task,
                planning_reason="passed_run_not_adopted",
                source_kind="run",
                source_run_id=run.id,
            ),
            rationale="当前任务已有可采纳结果，应该拆出显式收口任务，避免 run 通过但无人接手。",
        )

    def _build_compare_follow_up(self, task: Task, compare: ReviewCompare) -> PlannedTaskSuggestion:
        summary = self._short_text(compare.summary or compare.title, 140)
        return PlannedTaskSuggestion(
            title=f"根据 compare 推进：{self._short_text(task.title, 32)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    f"参考 compare：{compare.title}",
                    f"摘要：{summary}",
                    "基于这次 compare 的结论拆出下一轮实现或验证任务。",
                ]
            ),
            priority="high" if task.priority == "high" else "medium",
            labels=self._merge_labels(task.labels, "follow-up", "compare"),
            metadata=self._build_metadata(
                task,
                planning_reason="review_compare_follow_up",
                source_kind="compare",
                source_compare_id=compare.id,
            ),
            rationale="当前任务已经有 compare 结论，适合显式拆成下一轮可执行工作。",
        )

    def _build_generic_follow_up(self, task: Task) -> PlannedTaskSuggestion:
        return PlannedTaskSuggestion(
            title=f"继续推进：{self._short_text(task.title, 40)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    "当前还没有明确失败 run 或 compare 结论，先拆一张下一轮推进任务维持工作连续性。",
                ]
            ),
            priority=task.priority or "medium",
            labels=self._merge_labels(task.labels, "follow-up", "next-step"),
            metadata=self._build_metadata(
                task,
                planning_reason="task_next_step",
                source_kind="task",
            ),
            rationale="即使当前上下文不完整，也要能为下一轮推进预留任务入口。",
        )

    def _build_metadata(
        self,
        task: Task,
        *,
        planning_reason: str,
        source_kind: str,
        source_run_id: str | None = None,
        source_compare_id: str | None = None,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "parentTaskId": task.id,
            "sourceTaskId": task.id,
            "sourceKind": source_kind,
            "planningReason": planning_reason,
        }
        if source_run_id:
            metadata["sourceRunId"] = source_run_id
        if source_compare_id:
            metadata["sourceCompareId"] = source_compare_id
        return metadata

    def _merge_labels(self, labels: list[str] | None, *extra: str) -> list[str]:
        merged: list[str] = []
        for item in [*(labels or []), *extra]:
            value = item.strip()
            if value and value not in merged:
                merged.append(value)
        return merged[:6]

    def _metadata_signature(self, metadata: dict[str, object]) -> tuple[str, str, str]:
        return (
            str(metadata.get("planningReason", "")),
            str(metadata.get("sourceRunId", "")),
            str(metadata.get("sourceCompareId", "")),
        )

    def _short_text(self, value: str, limit: int) -> str:
        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 1]}…"
