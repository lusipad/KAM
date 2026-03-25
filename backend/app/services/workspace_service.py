"""
Lite 任务台服务
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.workspace import AgentRun, ContextSnapshot, RunArtifact, TaskCard, TaskRef
from app.services.run_executor import execution_manager


class WorkspaceService:
    def __init__(self, db: Session):
        self.db = db

    # ===== 任务 =====
    def list_tasks(self, status: str | None = None) -> list[TaskCard]:
        query = self.db.query(TaskCard)
        if status:
            query = query.filter(TaskCard.status == status)
        return query.order_by(TaskCard.updated_at.desc()).all()

    def create_task(self, data: dict[str, Any]) -> TaskCard:
        task = TaskCard(
            title=data["title"],
            description=data.get("description", ""),
            status=data.get("status", "inbox"),
            priority=data.get("priority", "medium"),
            tags=data.get("tags") or [],
            metadata_=data.get("metadata") or {},
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_task(self, task_id: str) -> TaskCard | None:
        return self.db.query(TaskCard).filter(TaskCard.id == task_id).first()

    def update_task(self, task_id: str, data: dict[str, Any]) -> TaskCard | None:
        task = self.get_task(task_id)
        if not task:
            return None

        for field, attr in {
            "title": "title",
            "description": "description",
            "status": "status",
            "priority": "priority",
        }.items():
            if field in data:
                setattr(task, attr, data[field])

        if "tags" in data:
            task.tags = data["tags"] or []
        if "metadata" in data:
            task.metadata_ = {**(task.metadata_ or {}), **(data["metadata"] or {})}

        self.db.commit()
        self.db.refresh(task)
        return task

    def archive_task(self, task_id: str) -> TaskCard | None:
        task = self.get_task(task_id)
        if not task:
            return None

        task.status = "archived"
        task.metadata_ = {
            **(task.metadata_ or {}),
            "archivedAt": datetime.utcnow().isoformat(),
        }
        self.db.commit()
        self.db.refresh(task)
        return task

    # ===== 引用 =====
    def add_task_ref(self, task_id: str, data: dict[str, Any]) -> TaskRef | None:
        task = self.get_task(task_id)
        if not task:
            return None

        ref = TaskRef(
            task_id=task.id,
            ref_type=data["type"],
            label=data["label"],
            value=data["value"],
            metadata_=data.get("metadata") or {},
        )
        self.db.add(ref)
        self.db.commit()
        self.db.refresh(ref)
        return ref

    def delete_task_ref(self, task_id: str, ref_id: str) -> bool:
        ref = self.db.query(TaskRef).filter(TaskRef.id == ref_id, TaskRef.task_id == task_id).first()
        if not ref:
            return False
        self.db.delete(ref)
        self.db.commit()
        return True

    # ===== 上下文 =====
    def resolve_context(self, task_id: str) -> ContextSnapshot | None:
        task = self.get_task(task_id)
        if not task:
            return None

        refs = [ref.to_dict() for ref in task.refs] if task.refs else []
        recent_runs = [run.to_dict(include_artifacts=False) for run in task.runs[:5]] if task.runs else []

        data = {
            "task": task.to_dict(include_relations=False),
            "refs": refs,
            "recentRuns": recent_runs,
        }
        summary = self._build_context_summary(task, refs, recent_runs)

        snapshot = ContextSnapshot(task_id=task.id, summary=summary, data=data)
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> ContextSnapshot | None:
        return self.db.query(ContextSnapshot).filter(ContextSnapshot.id == snapshot_id).first()

    # ===== Runs =====
    def list_runs(self, task_id: str | None = None, status: str | None = None) -> list[AgentRun]:
        query = self.db.query(AgentRun)
        if task_id:
            query = query.filter(AgentRun.task_id == task_id)
        if status:
            query = query.filter(AgentRun.status == status)
        return query.order_by(AgentRun.created_at.desc()).all()

    def get_run(self, run_id: str) -> AgentRun | None:
        return self.db.query(AgentRun).filter(AgentRun.id == run_id).first()

    def start_run(self, run_id: str) -> AgentRun | None:
        run = self.get_run(run_id)
        if not run:
            return None
        if execution_manager.launch_run(str(run.id)):
            self.db.expire(run)
            self.db.refresh(run)
            self._refresh_task_status(str(run.task_id))
            self.db.commit()
            self.db.refresh(run)
        return run

    def create_runs(self, task_id: str, agents: Iterable[dict[str, Any]]) -> list[AgentRun] | None:
        task = self.get_task(task_id)
        if not task:
            return None

        snapshot = self.resolve_context(task_id)
        prompt = self._build_prompt(task, snapshot)
        created_runs: list[AgentRun] = []

        for agent in agents:
            agent_name = agent.get("name") or agent.get("agentName")
            if not agent_name:
                continue

            agent_type = agent.get("type") or agent.get("agentType") or "custom"
            command = agent.get("command")
            workdir = self._create_workdir(task_id, agent_name)
            launch_plan = self._build_launch_plan(agent_type, command, workdir)

            run = AgentRun(
                task_id=task.id,
                agent_name=agent_name,
                agent_type=agent_type,
                status="planned",
                workdir=str(workdir),
                prompt=prompt,
                command=command,
                metadata_={
                    "requestedAt": datetime.utcnow().isoformat(),
                    "snapshotId": str(snapshot.id) if snapshot else None,
                    "launchPlan": launch_plan,
                },
            )
            self.db.add(run)
            self.db.flush()

            self._create_artifact(
                run,
                artifact_type="prompt",
                title=f"{agent_name} prompt",
                content=prompt,
                path=str(workdir / "prompt.md"),
            )
            (workdir / "prompt.md").write_text(prompt, encoding="utf-8")
            self._create_artifact(
                run,
                artifact_type="context",
                title=f"{agent_name} context",
                content=json.dumps(snapshot.data if snapshot else {}, ensure_ascii=False, indent=2),
                path=str(workdir / "context.json"),
            )
            (workdir / "context.json").write_text(
                json.dumps(snapshot.data if snapshot else {}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._create_artifact(
                run,
                artifact_type="plan",
                title=f"{agent_name} launch plan",
                content=launch_plan,
                path=str(workdir / "launch-plan.txt"),
            )
            (workdir / "launch-plan.txt").write_text(
                launch_plan,
                encoding="utf-8",
            )

            created_runs.append(run)

        self._refresh_task_status(str(task.id))
        self.db.commit()
        for run in created_runs:
            self.db.refresh(run)
        self.db.refresh(task)
        for run in created_runs:
            if execution_manager.launch_run(str(run.id)):
                self.db.expire(run)
                self.db.refresh(run)
        return created_runs

    def cancel_run(self, run_id: str) -> AgentRun | None:
        run = self.get_run(run_id)
        if not run:
            return None

        execution_manager.cancel_run(str(run.id))

        if run.status not in {"completed", "failed", "canceled"}:
            run.status = "canceled"
            run.completed_at = datetime.utcnow()
            run.error_message = run.error_message or "Run 已被用户取消"
            self._refresh_task_status(str(run.task_id))
            self.db.commit()
            self.db.refresh(run)
        return run

    def retry_run(self, run_id: str) -> AgentRun | None:
        previous_run = self.get_run(run_id)
        if not previous_run:
            return None

        clone = AgentRun(
            task_id=previous_run.task_id,
            agent_name=previous_run.agent_name,
            agent_type=previous_run.agent_type,
            status="planned",
            workdir=str(self._create_workdir(str(previous_run.task_id), previous_run.agent_name)),
            prompt=previous_run.prompt,
            command=previous_run.command,
            metadata_={
                **(previous_run.metadata_ or {}),
                "retryOf": str(previous_run.id),
                "requestedAt": datetime.utcnow().isoformat(),
            },
        )
        self.db.add(clone)
        self.db.flush()

        workdir = Path(clone.workdir)
        workdir.mkdir(parents=True, exist_ok=True)

        self._create_artifact(
            clone,
            artifact_type="prompt",
            title=f"{clone.agent_name} retry prompt",
            content=clone.prompt,
            path=str(workdir / "prompt.md"),
        )
        (workdir / "prompt.md").write_text(clone.prompt, encoding="utf-8")

        context_artifact = next(
            (artifact for artifact in previous_run.artifacts if artifact.artifact_type == "context"),
            None,
        )
        context_content = context_artifact.content if context_artifact else "{}"
        self._create_artifact(
            clone,
            artifact_type="context",
            title=f"{clone.agent_name} retry context",
            content=context_content,
            path=str(workdir / "context.json"),
        )
        (workdir / "context.json").write_text(context_content, encoding="utf-8")

        launch_plan = self._build_launch_plan(clone.agent_type, clone.command, workdir)
        self._create_artifact(
            clone,
            artifact_type="plan",
            title=f"{clone.agent_name} retry launch plan",
            content=launch_plan,
            path=str(workdir / "launch-plan.txt"),
        )
        (workdir / "launch-plan.txt").write_text(launch_plan, encoding="utf-8")

        self._refresh_task_status(str(clone.task_id))
        self.db.commit()
        self.db.refresh(clone)
        if execution_manager.launch_run(str(clone.id)):
            self.db.expire(clone)
            self.db.refresh(clone)
        return clone

    # ===== Review =====
    def get_review(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if not task:
            return None

        runs = [run.to_dict() for run in task.runs]
        artifacts = [artifact.to_dict() for run in task.runs for artifact in run.artifacts]
        summary_lines = [
            f"任务: {task.title}",
            f"状态: {task.status}",
            f"运行数: {len(runs)}",
        ]
        if task.refs:
            summary_lines.append(f"引用数: {len(task.refs)}")

        for run in task.runs[:5]:
            change_stats = self._extract_run_change_stats(run)
            suffix = ""
            if change_stats["changedFiles"]:
                suffix = f" ({change_stats['changedFiles']} files"
                if change_stats["hasPatch"]:
                    suffix += ", patch"
                if change_stats["untrackedFiles"]:
                    suffix += f", {change_stats['untrackedFiles']} untracked"
                suffix += ")"
            summary_lines.append(f"- {run.agent_name}: {run.status}{suffix}")

        return {
            "task": task.to_dict(),
            "runs": runs,
            "artifacts": artifacts,
            "summary": "\n".join(summary_lines),
        }

    def compare_runs(self, task_id: str) -> list[dict[str, Any]] | None:
        task = self.get_task(task_id)
        if not task:
            return None

        comparison = []
        for run in task.runs:
            change_stats = self._extract_run_change_stats(run)
            comparison.append(
                {
                    "runId": str(run.id),
                    "agentName": run.agent_name,
                    "status": run.status,
                    "artifactCount": len(run.artifacts or []),
                    "changedFiles": change_stats["changedFiles"],
                    "untrackedFiles": change_stats["untrackedFiles"],
                    "hasPatch": change_stats["hasPatch"],
                    "repoRoot": change_stats["repoRoot"],
                }
            )
        return comparison

    def hydrate_artifact(self, artifact: RunArtifact, max_chars: int | None = None) -> dict[str, Any]:
        payload = artifact.to_dict()
        if artifact.path:
            path = Path(artifact.path)
            if path.exists():
                content = path.read_text(encoding="utf-8", errors="replace")
                if max_chars is not None and len(content) > max_chars:
                    payload["content"] = content[-max_chars:]
                    payload["truncated"] = True
                    payload["tailChars"] = max_chars
                else:
                    payload["content"] = content
                    payload["truncated"] = False
                payload["size"] = len(content)
        return payload

    # ===== helpers =====
    def _build_context_summary(
        self,
        task: TaskCard,
        refs: list[dict[str, Any]],
        runs: list[dict[str, Any]],
    ) -> str:
        lines = [
            f"任务: {task.title}",
            f"优先级: {task.priority}",
            f"状态: {task.status}",
            "",
            "任务描述:",
            task.description or "无",
            "",
            f"引用数量: {len(refs)}",
            f"历史运行: {len(runs)}",
        ]
        if refs:
            lines.extend(["", "主要引用:"])
            lines.extend([f"- [{ref['type']}] {ref['label']}: {ref['value']}" for ref in refs[:5]])
        return "\n".join(lines)

    def _build_prompt(self, task: TaskCard, snapshot: ContextSnapshot | None) -> str:
        summary = snapshot.summary if snapshot else task.description
        return "\n".join(
            [
                f"# Task: {task.title}",
                "",
                "## Goal",
                task.description or "请根据当前任务完成工作。",
                "",
                "## Context",
                summary or "无上下文摘要。",
                "",
                "## Output Requirements",
                "- 给出关键结论",
                "- 标注风险与假设",
                "- 如有代码修改，说明涉及文件与建议后续动作",
            ]
        )

    def _create_workdir(self, task_id: str, agent_name: str) -> Path:
        safe_agent_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in agent_name.lower()).strip("-")
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        workroot = Path(settings.AGENT_WORKROOT)
        workdir = workroot / str(task_id) / f"{safe_agent_name}-{timestamp}"
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def _build_launch_plan(self, agent_type: str, command: str | None, workdir: Path) -> str:
        if command:
            return f"Agent type: {agent_type}\nWorkdir: {workdir}\nCommand: {command}"

        if agent_type == "codex":
            command_line = (
                f"{settings.CODEX_CLI_PATH} exec --skip-git-repo-check --full-auto "
                f"--output-last-message {workdir / 'final.md'} -C <execution_cwd> <prompt>"
            )
        elif agent_type in {"claude", "claude-code"}:
            command_line = (
                f"{settings.CLAUDE_CODE_CLI_PATH} -p --permission-mode bypassPermissions "
                "--output-format text <prompt>"
            )
        else:
            command_line = "No built-in adapter. Please provide a custom command."

        return (
            f"Agent type: {agent_type}\n"
            f"Workdir: {workdir}\n"
            f"Adapter command: {command_line}"
        )

    def _create_artifact(
        self,
        run: AgentRun,
        artifact_type: str,
        title: str,
        content: str,
        path: str | None = None,
    ) -> RunArtifact:
        artifact = RunArtifact(
            run_id=run.id,
            artifact_type=artifact_type,
            title=title,
            content=content,
            path=path,
        )
        self.db.add(artifact)
        return artifact

    def _extract_run_change_stats(self, run: AgentRun) -> dict[str, Any]:
        changes_artifact = next((artifact for artifact in run.artifacts if artifact.artifact_type == "changes"), None)
        patch_artifact = next((artifact for artifact in run.artifacts if artifact.artifact_type == "patch"), None)
        metadata = changes_artifact.metadata_ if changes_artifact else {}
        return {
            "changedFiles": metadata.get("changed", 0),
            "untrackedFiles": metadata.get("untracked", 0),
            "hasPatch": bool(patch_artifact or metadata.get("trackedDiff")),
            "repoRoot": metadata.get("repoRoot"),
        }

    def _refresh_task_status(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return

        runs = task.runs or []
        statuses = {run.status for run in runs}
        if not runs:
            task.status = "ready"
        elif statuses & {"running", "queued", "planned"}:
            task.status = "running"
        else:
            task.status = "review"
