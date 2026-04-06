from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import ContextSnapshot, ReviewCompare, Task, TaskRef, TaskRun, TaskRunArtifact, now
from services.task_dependencies import build_task_dependency_state, load_tasks_by_id


@dataclass
class SuggestedTaskRef:
    kind: str
    label: str
    value: str
    metadata: dict[str, object] | None = None

    def signature(self) -> tuple[str, str, str]:
        return self.kind, self.label, self.value

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "value": self.value,
            "metadata": self.metadata or {},
        }


@dataclass
class PlannedTaskSuggestion:
    title: str
    description: str
    priority: str
    labels: list[str]
    metadata: dict[str, object]
    rationale: str
    recommended_prompt: str
    recommended_agent: str
    acceptance_checks: list[str]
    suggested_refs: list[SuggestedTaskRef]

    def signature(self) -> tuple[str, str, str]:
        return (
            str(self.metadata.get("planningReason", "")),
            str(self.metadata.get("sourceRunId", "")),
            str(self.metadata.get("sourceCompareId", "")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "labels": self.labels,
            "metadata": self.metadata,
            "rationale": self.rationale,
            "recommendedPrompt": self.recommended_prompt,
            "recommendedAgent": self.recommended_agent,
            "acceptanceChecks": self.acceptance_checks,
            "suggestedRefs": [item.to_dict() for item in self.suggested_refs],
        }


@dataclass(frozen=True)
class _SuggestionCandidate:
    suggestion: PlannedTaskSuggestion
    rank: tuple[int, float]


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
        if self._is_terminal_task(task):
            return task, [], []
        tasks_by_id = await load_tasks_by_id(self.db)
        if not build_task_dependency_state(task, tasks_by_id).ready:
            return task, [], []

        latest_snapshot = task.snapshots[-1] if task.snapshots else None
        run_artifacts_by_run_id = await self._load_run_artifacts([run.id for run in task.runs])
        existing_signatures = {
            self._metadata_signature(item.metadata_ or {})
            for item in await self._list_existing_follow_ups(task.id)
        }
        suggestions = self._build_suggestions(
            task,
            existing_signatures,
            latest_snapshot,
            run_artifacts_by_run_id,
            max(1, limit),
        )

        if not create_tasks or not suggestions:
            return task, suggestions, []

        created_pairs: list[tuple[Task, PlannedTaskSuggestion]] = []
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
            created_pairs.append((created, suggestion))

        await self.db.flush()

        created_tasks: list[Task] = []
        for created, suggestion in created_pairs:
            for ref in suggestion.suggested_refs:
                self.db.add(
                    TaskRef(
                        task_id=created.id,
                        kind=ref.kind,
                        label=ref.label,
                        value=ref.value,
                        metadata_=ref.metadata,
                    )
                )
            created.updated_at = now()
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

    async def _load_run_artifacts(self, run_ids: list[str]) -> dict[str, list[TaskRunArtifact]]:
        if not run_ids:
            return {}
        result = await self.db.execute(
            select(TaskRunArtifact)
            .where(TaskRunArtifact.task_run_id.in_(run_ids))
            .order_by(TaskRunArtifact.created_at.asc())
        )
        artifacts_by_run_id: dict[str, list[TaskRunArtifact]] = {}
        for artifact in result.scalars():
            artifacts_by_run_id.setdefault(artifact.task_run_id, []).append(artifact)
        return artifacts_by_run_id

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
        latest_snapshot: ContextSnapshot | None,
        run_artifacts_by_run_id: dict[str, list[TaskRunArtifact]],
        limit: int,
    ) -> list[PlannedTaskSuggestion]:
        candidates: list[_SuggestionCandidate] = []
        runs_by_id = {run.id: run for run in task.runs}

        latest_terminal_run = self._latest_terminal_run(task)
        if latest_terminal_run is not None and latest_terminal_run.status == "failed":
            candidates.append(
                _SuggestionCandidate(
                    suggestion=self._build_failed_run_follow_up(
                        task,
                        latest_terminal_run,
                        latest_snapshot,
                        run_artifacts_by_run_id.get(latest_terminal_run.id, []),
                    ),
                    rank=(
                        self._suggestion_reason_rank("failed_run_follow_up"),
                        -latest_terminal_run.created_at.timestamp(),
                    ),
                )
            )

        if latest_terminal_run is not None and latest_terminal_run.status == "passed" and latest_terminal_run.adopted_at is None:
            candidates.append(
                _SuggestionCandidate(
                    suggestion=self._build_adopt_follow_up(
                        task,
                        latest_terminal_run,
                        latest_snapshot,
                        run_artifacts_by_run_id.get(latest_terminal_run.id, []),
                    ),
                    rank=(
                        self._suggestion_reason_rank("passed_run_not_adopted"),
                        -latest_terminal_run.created_at.timestamp(),
                    ),
                )
            )

        latest_compare = task.review_compares[-1] if task.review_compares else None
        if latest_compare is not None:
            candidates.append(
                _SuggestionCandidate(
                    suggestion=self._build_compare_follow_up(
                        task,
                        latest_compare,
                        latest_snapshot,
                        runs_by_id,
                        run_artifacts_by_run_id,
                    ),
                    rank=(
                        self._suggestion_reason_rank("review_compare_follow_up"),
                        -latest_compare.created_at.timestamp(),
                    ),
                )
            )

        if not candidates:
            candidates.append(
                _SuggestionCandidate(
                    suggestion=self._build_generic_follow_up(task, latest_snapshot),
                    rank=(
                        self._suggestion_reason_rank("task_next_step"),
                        -task.updated_at.timestamp(),
                    ),
                )
            )

        candidates.sort(key=lambda item: item.rank)

        unique_suggestions: list[PlannedTaskSuggestion] = []
        seen_signatures = set(existing_signatures)
        for candidate in candidates:
            suggestion = candidate.suggestion
            signature = suggestion.signature()
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique_suggestions.append(suggestion)
            if len(unique_suggestions) >= limit:
                break

        return unique_suggestions

    def _build_failed_run_follow_up(
        self,
        task: Task,
        run: TaskRun,
        latest_snapshot: ContextSnapshot | None,
        artifacts: list[TaskRunArtifact],
    ) -> PlannedTaskSuggestion:
        run_summary = self._run_summary(run, artifacts)
        failure_excerpt = self._run_log_excerpt(run, artifacts, 160)
        changed_files = self._top_files(run.changed_files, 3)
        acceptance_checks = [
            f"定位并消除失败 run {run.id} 的直接原因",
            "补齐必要改动，并明确这轮修复覆盖到哪些文件或验证",
            "至少运行一项相关验证，确认父任务不再被这个失败阻塞",
        ]
        suggested_refs = self._suggested_refs(
            task,
            latest_snapshot=latest_snapshot,
            source_run=run,
            preferred_files=changed_files,
            note_summary=run_summary,
        )
        prompt = self._compose_prompt(
            directive="修复失败 run，先消除阻塞再继续父任务。",
            task=task,
            evidence_lines=[
                f"失败 run：{run.id} · {run.agent}",
                f"上次任务：{self._short_text(run.task, 200)}",
                f"失败摘要：{run_summary}",
                self._optional_line("日志片段", failure_excerpt),
                self._optional_line("涉及文件", ", ".join(changed_files)),
                self._optional_line("最近快照", latest_snapshot.summary if latest_snapshot else None),
            ],
            acceptance_checks=acceptance_checks,
        )
        return PlannedTaskSuggestion(
            title=f"修复失败 run：{self._short_text(run.task, 40)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    f"失败 run：{run.agent} · {run_summary}",
                    "先拆出一张修复任务，避免主链路继续积压在已知失败上。",
                ]
            ),
            priority="high",
            labels=self._merge_labels(task.labels, "follow-up", "failure"),
            metadata=self._build_metadata(
                task,
                planning_reason="failed_run_follow_up",
                source_kind="run",
                source_run_id=run.id,
                recommended_prompt=prompt,
                recommended_agent="codex",
                acceptance_checks=acceptance_checks,
                suggested_refs=suggested_refs,
            ),
            rationale="最近一轮 run 失败，需要先把阻塞点显式拆出来并形成修复任务。",
            recommended_prompt=prompt,
            recommended_agent="codex",
            acceptance_checks=acceptance_checks,
            suggested_refs=suggested_refs,
        )

    def _build_adopt_follow_up(
        self,
        task: Task,
        run: TaskRun,
        latest_snapshot: ContextSnapshot | None,
        artifacts: list[TaskRunArtifact],
    ) -> PlannedTaskSuggestion:
        run_summary = self._run_summary(run, artifacts)
        changed_files = self._top_files(run.changed_files, 4)
        acceptance_checks = [
            "复核当前实现是否已经覆盖父任务目标，并补齐缺口",
            "至少运行一项相关验证，再给出是否可 adopt 的结论",
            "如果仍不能收口，明确下一轮要继续推进的边界",
        ]
        suggested_refs = self._suggested_refs(
            task,
            latest_snapshot=latest_snapshot,
            source_run=run,
            preferred_files=changed_files,
            note_summary=run_summary,
        )
        prompt = self._compose_prompt(
            directive="收口父任务的现有实现，并把下一轮动作落到代码或验证上。",
            task=task,
            evidence_lines=[
                f"待收口 run：{run.id} · {run.agent}",
                f"结果摘要：{run_summary}",
                self._optional_line("涉及文件", ", ".join(changed_files)),
                self._optional_line("最近快照", latest_snapshot.summary if latest_snapshot else None),
            ],
            acceptance_checks=acceptance_checks,
        )
        return PlannedTaskSuggestion(
            title=f"采纳并验证：{self._short_text(run_summary, 42)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    f"待采纳 run：{run.agent} · {run_summary}",
                    f"涉及文件：{', '.join(changed_files) or '无文件列表'}",
                    "优先复核已有实现，再决定 adopt、补丁式修订或继续拆分。",
                ]
            ),
            priority="high" if task.priority == "high" else "medium",
            labels=self._merge_labels(task.labels, "follow-up", "adopt"),
            metadata=self._build_metadata(
                task,
                planning_reason="passed_run_not_adopted",
                source_kind="run",
                source_run_id=run.id,
                recommended_prompt=prompt,
                recommended_agent="codex",
                acceptance_checks=acceptance_checks,
                suggested_refs=suggested_refs,
            ),
            rationale="当前任务已经有通过但未采纳的结果，应该把收口动作单独显式化。",
            recommended_prompt=prompt,
            recommended_agent="codex",
            acceptance_checks=acceptance_checks,
            suggested_refs=suggested_refs,
        )

    def _build_compare_follow_up(
        self,
        task: Task,
        compare: ReviewCompare,
        latest_snapshot: ContextSnapshot | None,
        runs_by_id: dict[str, TaskRun],
        run_artifacts_by_run_id: dict[str, list[TaskRunArtifact]],
    ) -> PlannedTaskSuggestion:
        compare_summary = self._short_text(compare.summary or compare.title, 180)
        compared_runs = [runs_by_id[run_id] for run_id in compare.run_ids if run_id in runs_by_id]
        compared_files = self._top_files(
            [path for run in compared_runs for path in (run.changed_files or [])],
            4,
        )
        compared_run_summaries = "; ".join(
            self._short_text(self._run_summary(run, run_artifacts_by_run_id.get(run.id, [])), 80)
            for run in compared_runs[:2]
        )
        acceptance_checks = [
            "把 compare 结论收敛成这轮明确的实现范围或验证范围",
            "优先处理 compare 里暴露分歧或重复最多的文件",
            "完成后更新结论，必要时补一轮新的 compare 或 run",
        ]
        suggested_refs = self._suggested_refs(
            task,
            latest_snapshot=latest_snapshot,
            source_compare=compare,
            preferred_files=compared_files,
            note_summary=compare_summary,
        )
        prompt = self._compose_prompt(
            directive="根据 compare 结论继续推进父任务，优先把差异收敛成明确动作。",
            task=task,
            evidence_lines=[
                f"来源 compare：{compare.title}",
                f"compare 摘要：{compare_summary}",
                self._optional_line("相关 runs", compared_run_summaries),
                self._optional_line("候选文件", ", ".join(compared_files)),
                self._optional_line("最近快照", latest_snapshot.summary if latest_snapshot else None),
            ],
            acceptance_checks=acceptance_checks,
        )
        return PlannedTaskSuggestion(
            title=f"根据 compare 推进：{self._short_text(task.title, 32)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    f"参考 compare：{compare.title}",
                    f"摘要：{compare_summary}",
                    "把 compare 已经给出的判断变成下一轮具体实现或验证动作。",
                ]
            ),
            priority="high" if task.priority == "high" else "medium",
            labels=self._merge_labels(task.labels, "follow-up", "compare"),
            metadata=self._build_metadata(
                task,
                planning_reason="review_compare_follow_up",
                source_kind="compare",
                source_compare_id=compare.id,
                recommended_prompt=prompt,
                recommended_agent="codex",
                acceptance_checks=acceptance_checks,
                suggested_refs=suggested_refs,
            ),
            rationale="当前任务已经有 compare 结论，适合直接生成下一轮可执行工作。",
            recommended_prompt=prompt,
            recommended_agent="codex",
            acceptance_checks=acceptance_checks,
            suggested_refs=suggested_refs,
        )

    def _build_generic_follow_up(
        self,
        task: Task,
        latest_snapshot: ContextSnapshot | None,
    ) -> PlannedTaskSuggestion:
        parent_refs = ", ".join(ref.label for ref in task.refs[:3]) or "暂无 refs"
        acceptance_checks = [
            "把下一步推进落实成明确改动或验证，而不是停留在描述层",
            "如果当前上下文不够，先补 refs 或 snapshot 再执行",
            "产出可继续比较、采纳或拆分的结果，避免任务空转",
        ]
        suggested_refs = self._suggested_refs(
            task,
            latest_snapshot=latest_snapshot,
            note_summary=self._short_text(task.description or task.title, 160),
        )
        prompt = self._compose_prompt(
            directive="继续推进父任务，把当前上下文收敛成一轮具体的实现或验证。",
            task=task,
            evidence_lines=[
                f"当前任务状态：{task.status} · 优先级：{task.priority}",
                self._optional_line("任务描述", self._short_text(task.description or "", 180)),
                self._optional_line("已有 refs", parent_refs),
                self._optional_line("最近快照", latest_snapshot.summary if latest_snapshot else None),
            ],
            acceptance_checks=acceptance_checks,
        )
        return PlannedTaskSuggestion(
            title=f"继续推进：{self._short_text(task.title, 40)}",
            description="\n".join(
                [
                    f"上游任务：{task.title}",
                    "当前还没有明确失败 run 或 compare 结论，先拆一张下一轮推进任务维持连续性。",
                ]
            ),
            priority=task.priority or "medium",
            labels=self._merge_labels(task.labels, "follow-up", "next-step"),
            metadata=self._build_metadata(
                task,
                planning_reason="task_next_step",
                source_kind="task",
                recommended_prompt=prompt,
                recommended_agent="codex",
                acceptance_checks=acceptance_checks,
                suggested_refs=suggested_refs,
            ),
            rationale="即使当前上下文不完整，也应该为下一轮推进准备可直接执行的任务。",
            recommended_prompt=prompt,
            recommended_agent="codex",
            acceptance_checks=acceptance_checks,
            suggested_refs=suggested_refs,
        )

    def _build_metadata(
        self,
        task: Task,
        *,
        planning_reason: str,
        source_kind: str,
        recommended_prompt: str,
        recommended_agent: str,
        acceptance_checks: list[str],
        suggested_refs: list[SuggestedTaskRef],
        source_run_id: str | None = None,
        source_compare_id: str | None = None,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "parentTaskId": task.id,
            "sourceTaskId": task.id,
            "sourceKind": source_kind,
            "planningReason": planning_reason,
            "recommendedPrompt": recommended_prompt,
            "recommendedAgent": recommended_agent,
            "acceptanceChecks": acceptance_checks,
            "suggestedRefs": [item.to_dict() for item in suggested_refs],
        }
        if source_run_id:
            metadata["sourceRunId"] = source_run_id
        if source_compare_id:
            metadata["sourceCompareId"] = source_compare_id
        return metadata

    def _suggested_refs(
        self,
        task: Task,
        *,
        latest_snapshot: ContextSnapshot | None = None,
        source_run: TaskRun | None = None,
        source_compare: ReviewCompare | None = None,
        preferred_files: list[str] | None = None,
        note_summary: str | None = None,
    ) -> list[SuggestedTaskRef]:
        suggested_refs: list[SuggestedTaskRef] = []
        seen = set()

        def add_ref(ref: SuggestedTaskRef) -> None:
            signature = ref.signature()
            if signature in seen:
                return
            seen.add(signature)
            suggested_refs.append(ref)

        if latest_snapshot is not None:
            add_ref(
                SuggestedTaskRef(
                    kind="snapshot",
                    label="最近快照",
                    value=latest_snapshot.summary,
                    metadata={
                        "snapshotId": latest_snapshot.id,
                        "focus": latest_snapshot.focus or "",
                    },
                )
            )

        for ref in task.refs[:2]:
            add_ref(
                SuggestedTaskRef(
                    kind=ref.kind,
                    label=f"父任务 · {ref.label}",
                    value=ref.value,
                    metadata={
                        "sourceTaskId": task.id,
                        "sourceRefId": ref.id,
                        **(ref.metadata_ or {}),
                    },
                )
            )

        for file_path in self._top_files(preferred_files, 3):
            add_ref(
                SuggestedTaskRef(
                    kind="file",
                    label="候选文件",
                    value=file_path,
                    metadata={"source": "planner"},
                )
            )

        if source_run is not None:
            add_ref(
                SuggestedTaskRef(
                    kind="run",
                    label=f"来源 Run · {source_run.agent}",
                    value=source_run.id,
                    metadata={
                        "runId": source_run.id,
                        "status": source_run.status,
                    },
                )
            )

        if source_compare is not None:
            add_ref(
                SuggestedTaskRef(
                    kind="compare",
                    label="来源 Compare",
                    value=source_compare.id,
                    metadata={
                        "compareId": source_compare.id,
                        "title": source_compare.title,
                    },
                )
            )

        if note_summary:
            add_ref(
                SuggestedTaskRef(
                    kind="note",
                    label="上次结论",
                    value=note_summary,
                    metadata={"source": "planner"},
                )
            )

        return suggested_refs[:6]

    def _compose_prompt(
        self,
        *,
        directive: str,
        task: Task,
        evidence_lines: list[str | None],
        acceptance_checks: list[str],
    ) -> str:
        lines = [directive, f"父任务：{task.title}"]
        if task.description:
            lines.append(f"任务描述：{self._short_text(task.description, 200)}")
        if task.repo_path:
            lines.append(f"仓库：{task.repo_path}")
        for line in evidence_lines:
            if line:
                lines.append(line)
        lines.append("这轮完成标准：")
        for item in acceptance_checks:
            lines.append(f"- {item}")
        return "\n".join(lines)

    def _run_summary(self, run: TaskRun, artifacts: list[TaskRunArtifact]) -> str:
        artifact_summary = self._artifact_excerpt(artifacts, ("summary", "stdout", "task"), 180)
        return artifact_summary or self._short_text(run.result_summary or run.task, 180)

    def _run_log_excerpt(self, run: TaskRun, artifacts: list[TaskRunArtifact], limit: int) -> str | None:
        stdout = self._artifact_excerpt(artifacts, ("stdout",), limit)
        if stdout:
            return stdout
        last_line = self._last_nonempty_line(run.raw_output or "")
        if last_line:
            return self._short_text(last_line, limit)
        return None

    def _artifact_excerpt(
        self,
        artifacts: list[TaskRunArtifact],
        preferred_types: tuple[str, ...],
        limit: int,
    ) -> str | None:
        for artifact_type in preferred_types:
            for artifact in reversed(artifacts):
                if artifact.type != artifact_type:
                    continue
                compact = self._short_text(artifact.content, limit)
                if compact:
                    return compact
        return None

    def _top_files(self, values: list[str] | None, limit: int) -> list[str]:
        seen = set()
        files: list[str] = []
        for value in values or []:
            compact = value.strip()
            if not compact or compact in seen:
                continue
            seen.add(compact)
            files.append(compact)
            if len(files) >= limit:
                break
        return files

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

    def _latest_terminal_run(self, task: Task) -> TaskRun | None:
        for run in reversed(task.runs):
            if run.status in {"failed", "passed"}:
                return run
        return None

    def _suggestion_reason_rank(self, reason: str) -> int:
        if reason == "failed_run_follow_up":
            return 0
        if reason == "passed_run_not_adopted":
            return 1
        if reason == "review_compare_follow_up":
            return 2
        if reason == "task_next_step":
            return 3
        return 4

    def _optional_line(self, label: str, value: str | None) -> str | None:
        if not value:
            return None
        return f"{label}：{value}"

    def _is_terminal_task(self, task: Task) -> bool:
        return task.status in {"archived", "done", "verified", "blocked"}

    def _last_nonempty_line(self, value: str) -> str | None:
        for line in reversed(value.splitlines()):
            compact = line.strip()
            if compact:
                return compact
        return None

    def _short_text(self, value: str, limit: int) -> str:
        compact = " ".join(value.split())
        if not compact:
            return ""
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 1]}…"
