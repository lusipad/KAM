from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from db import async_session
from models import Task, TaskRun, now
from services.artifact_store import ArtifactStore
from services.digest import DigestService
from services.task_autodrive import (
    schedule_autodrive_for_task,
    schedule_global_autodrive_if_enabled,
    wait_for_background_autodrive,
)
from services.task_context import TaskContextService


@dataclass
class _RunState:
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(settings.max_concurrent_runs))
    tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    initial_artifacts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class _ExecutionTarget:
    remote_url: str
    ref: str
    head_sha: str | None = None
    push_on_success: bool = False


@dataclass(frozen=True)
class _FinalizeSuccessResult:
    changed_files: list[str]
    patch_output: str = ""
    auto_adopted: bool = False
    task_status: str | None = None


_STATE = _RunState()


class RunEngine:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_task_run(
        self,
        *,
        task_id: str,
        agent: str,
        task: str,
        initial_artifacts: list[dict[str, Any]] | None = None,
    ) -> TaskRun:
        run = TaskRun(task_id=task_id, agent=agent, task=task, status="pending")
        self.db.add(run)
        task_record = await self.db.get(Task, task_id)
        if task_record is not None:
            if task_record.status in {"open", "failed"}:
                task_record.status = "in_progress"
            task_record.updated_at = now()
        await self.db.commit()
        await self.db.refresh(run)
        if initial_artifacts:
            _STATE.initial_artifacts[run.id] = [dict(artifact) for artifact in initial_artifacts]
        if settings.is_test_env:
            await self._execute_task_run(run.id)
            await self.db.refresh(run)
            return run
        task_handle = asyncio.create_task(self._execute_task_run(run.id))
        _STATE.tasks[run.id] = task_handle
        return run

    async def retry_run(self, run_id: str) -> TaskRun | None:
        task_run = await self.db.get(TaskRun, run_id)
        if task_run is None:
            return None
        return await self.create_task_run(
            task_id=task_run.task_id,
            agent=task_run.agent,
            task=task_run.task,
            initial_artifacts=await self.build_task_initial_artifacts(task_run.task_id),
        )

    async def build_task_initial_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.snapshots))
        )
        task_record = result.scalars().first()
        if task_record is None:
            return []

        snapshot = task_record.snapshots[-1] if task_record.snapshots else await TaskContextService(self.db).build_snapshot(task_record.id)
        artifacts: list[dict[str, Any]] = [
            {
                "type": "task_snapshot",
                "content": json.dumps(
                    {
                        "taskId": task_record.id,
                        "title": task_record.title,
                        "status": task_record.status,
                        "priority": task_record.priority,
                        "repoPath": task_record.repo_path,
                        "labels": task_record.labels or [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        ]
        source_context_artifact = self._build_source_context_artifact(task_record.metadata_ or {})
        if source_context_artifact is not None:
            artifacts.append(source_context_artifact)
        if snapshot is not None:
            artifacts.append(
                {
                    "type": "context_snapshot",
                    "content": snapshot.content,
                    "metadata": {"snapshotId": snapshot.id, "summary": snapshot.summary, "focus": snapshot.focus},
                }
            )
        return artifacts

    async def adopt_run(self, run_id: str) -> dict[str, Any]:
        task_run = await self.db.get(TaskRun, run_id)
        if task_run is None:
            return {"ok": False, "error": "run_not_found"}
        return await self._adopt_task_run(task_run)

    async def _adopt_task_run(self, run: TaskRun) -> dict[str, Any]:
        if run.status != "passed":
            return {"ok": False, "error": "only_passed_runs_can_be_adopted"}
        if run.adopted_at is not None:
            return {"ok": True, "adoptedAt": run.adopted_at.isoformat()}

        task_record = await self.db.get(Task, run.task_id)
        repo_path = Path(task_record.repo_path) if task_record and task_record.repo_path else None
        worktree_path = Path(run.worktree_path) if run.worktree_path else None
        if repo_path is None or worktree_path is None or not repo_path.exists() or not worktree_path.exists():
            return {"ok": False, "error": "run_has_no_git_worktree"}

        branch = self._branch_name(run.id)
        try:
            self._git(repo_path, "merge", "--ff-only", branch)
            self._git(repo_path, "worktree", "remove", str(worktree_path), "--force")
            self._git(repo_path, "branch", "-D", branch)
        except subprocess.CalledProcessError as exc:
            return {"ok": False, "error": exc.stderr.strip() or exc.stdout.strip() or "git_merge_failed"}

        run.adopted_at = now()
        if task_record is not None:
            task_record.updated_at = now()
        await self.db.commit()
        return {"ok": True, "adoptedAt": run.adopted_at.isoformat()}

    async def _execute_task_run(self, run_id: str) -> None:
        async with _STATE.semaphore:
            auto_drive_task_id: str | None = None
            try:
                async with async_session() as session:
                    run = await self._load_task_run(session, run_id)
                    if run is None:
                        return
                    task_record = run.task_rel
                    run.status = "running"
                    if task_record is not None:
                        task_record.updated_at = now()
                    await session.commit()

                    started_at = asyncio.get_event_loop().time()
                    if settings.mock_runs:
                        self._apply_mock_run_result(run, started_at)
                        await ArtifactStore(session).replace_for_run(run.id, self._build_artifacts(run, ""))
                        if task_record is not None:
                            task_record.updated_at = now()
                        await session.commit()
                        auto_drive_task_id = run.task_id
                        return

                    worktree_path, command = await self._prepare_task_execution(run, task_record)
                    patch_output = ""
                    execution_target = self._task_execution_target(task_record)
                    if worktree_path is not None:
                        run.worktree_path = str(worktree_path)
                        await session.commit()

                    code, output = await self._run_command(command, worktree_path or settings.run_dir)
                    run.duration_ms = int((asyncio.get_event_loop().time() - started_at) * 1000)
                    run.raw_output = output[-20000:]

                    repo_path = Path(task_record.repo_path).resolve() if task_record and task_record.repo_path else None
                    if code == 0:
                        finalize_result = await self._finalize_success(
                            run,
                            task_record,
                            repo_path,
                            worktree_path,
                            execution_target,
                        )
                        run.status = "passed"
                        run.changed_files = finalize_result.changed_files
                        run.check_passed = True
                        patch_output = finalize_result.patch_output
                        if finalize_result.auto_adopted:
                            run.adopted_at = now()
                        if task_record is not None and finalize_result.task_status:
                            task_record.status = finalize_result.task_status
                    else:
                        run.status = "failed"
                        run.check_passed = False
                        run.changed_files = []

                    run.result_summary = await DigestService(session).summarize_run(run)
                    await ArtifactStore(session).replace_for_run(run.id, self._build_artifacts(run, patch_output))
                    if task_record is not None:
                        task_record.updated_at = now()
                    await session.commit()
                    auto_drive_task_id = run.task_id
            except Exception as exc:
                async with async_session() as session:
                    run = await self._load_task_run(session, run_id)
                    if run is not None:
                        run.status = "failed"
                        run.check_passed = False
                        run.raw_output = f"{run.raw_output or ''}\n{type(exc).__name__}: {exc}".strip()
                        run.result_summary = f"执行失败：{type(exc).__name__}: {exc}"
                        if run.task_rel is not None:
                            run.task_rel.updated_at = now()
                        await session.commit()
                        auto_drive_task_id = run.task_id
            finally:
                _STATE.tasks.pop(run_id, None)
                _STATE.initial_artifacts.pop(run_id, None)
                if auto_drive_task_id is not None:
                    try:
                        global_enabled = await schedule_global_autodrive_if_enabled()
                        if not global_enabled:
                            await schedule_autodrive_for_task(auto_drive_task_id)
                    except Exception:
                        pass

    async def _prepare_task_execution(self, run: TaskRun, task_record: Task | None) -> tuple[Path | None, list[str]]:
        repo_path = Path(task_record.repo_path).resolve() if task_record and task_record.repo_path else None
        execution_target = self._task_execution_target(task_record)
        return await self._prepare_workspace(run.id, run.agent, run.task, repo_path, execution_target)

    async def _prepare_workspace(
        self,
        run_id: str,
        agent: str,
        task: str,
        repo_path: Path | None,
        execution_target: _ExecutionTarget | None = None,
    ) -> tuple[Path | None, list[str]]:
        if repo_path and repo_path.exists() and (repo_path / ".git").exists():
            worktree_path = settings.run_dir / run_id
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            branch = self._branch_name(run_id)
            start_point = "HEAD"
            if execution_target is not None:
                start_point = self._resolve_execution_start_point(repo_path, execution_target)
            self._git(repo_path, "worktree", "add", "-b", branch, str(worktree_path), start_point)
            command = self._build_command(agent, task, worktree_path)
            return worktree_path, command

        scratch = settings.run_dir / run_id
        scratch.mkdir(parents=True, exist_ok=True)
        command = self._build_command(agent, task, scratch)
        return None, command

    def _build_command(self, agent: str, task: str, cwd: Path) -> list[str]:
        if agent == "codex":
            return [
                self._resolve_agent_binary(settings.codex_path),
                "exec",
                "--json",
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
                "--cd",
                str(cwd),
                task,
            ]
        if agent == "claude-code":
            return [
                self._resolve_agent_binary(settings.claude_code_path),
                "-p",
                "--dangerously-skip-permissions",
                "--output-format",
                "text",
                task,
            ]
        raise RuntimeError(f"unsupported_agent:{agent}")

    def _resolve_agent_binary(self, executable: str) -> str:
        candidate = Path(executable)
        if candidate.is_file():
            return str(candidate)

        if os.name == "nt" and not candidate.suffix:
            for suffix in (".cmd", ".exe", ".bat"):
                resolved = shutil.which(f"{executable}{suffix}")
                if resolved:
                    return resolved

        return shutil.which(executable) or executable

    async def _run_command(self, command: list[str], cwd: Path) -> tuple[int, str]:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output_lines: list[str] = []
        assert process.stdout is not None
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            extracted = self._extract_output_text(line)
            output_lines.append(extracted)
        code = await process.wait()
        return code, "\n".join(output_lines)

    async def _finalize_success(
        self,
        run: TaskRun,
        task_record: Task | None,
        repo_path: Path | None,
        worktree_path: Path | None,
        execution_target: _ExecutionTarget | None = None,
    ) -> _FinalizeSuccessResult:
        if repo_path is None or worktree_path is None or not worktree_path.exists():
            return _FinalizeSuccessResult(changed_files=[])
        changed_files = self._git_output(worktree_path, "status", "--short")
        if not changed_files.strip():
            if execution_target is not None and execution_target.push_on_success:
                self._cleanup_worktree_branch(repo_path, worktree_path, run.id)
                return _FinalizeSuccessResult(
                    changed_files=[],
                    auto_adopted=True,
                    task_status="verified",
                )
            return _FinalizeSuccessResult(changed_files=[])
        self._git(worktree_path, "config", "user.name", settings.git_user_name)
        self._git(worktree_path, "config", "user.email", settings.git_user_email)
        self._git(worktree_path, "add", "-A")
        message_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as handle:
                handle.write(self._build_commit_message(run, task_record, execution_target))
                message_path = Path(handle.name)
            self._git(worktree_path, "commit", "-F", str(message_path))
        finally:
            if message_path is not None:
                message_path.unlink(missing_ok=True)
        committed_files = [line.strip() for line in self._git_output(worktree_path, "show", "--pretty=", "--name-only", "HEAD").splitlines() if line.strip()]
        patch_output = self._capture_patch(worktree_path)
        if execution_target is not None and execution_target.push_on_success:
            remote_name = self._ensure_remote(repo_path, execution_target.remote_url)
            self._git(worktree_path, "push", remote_name, f"HEAD:refs/heads/{execution_target.ref}")
            self._cleanup_worktree_branch(repo_path, worktree_path, run.id)
            return _FinalizeSuccessResult(
                changed_files=committed_files,
                patch_output=patch_output,
                auto_adopted=True,
                task_status="verified",
            )
        return _FinalizeSuccessResult(changed_files=committed_files, patch_output=patch_output)

    def _build_commit_message(
        self,
        run: TaskRun,
        task_record: Task | None,
        execution_target: _ExecutionTarget | None = None,
    ) -> str:
        task_title = (task_record.title.strip() if task_record and task_record.title else "") or f"task {run.task_id}"
        repo_path = task_record.repo_path.strip() if task_record and task_record.repo_path else None
        narrative = [
            f"This automated harness run completed successfully for {task_title}.",
            f"Run task: {run.task.strip()}",
        ]
        if repo_path:
            narrative.append(f"Repository: {repo_path}")
        if execution_target is not None and execution_target.push_on_success:
            narrative.append(f"Push target: {execution_target.remote_url}#{execution_target.ref}")

        constraint = "Harness-generated commits must remain adoptable from isolated worktrees"
        directive = "Review the associated artifacts before adopting this run into the main worktree"
        not_tested = "Manual validation after adopt into the main worktree"
        if execution_target is not None and execution_target.push_on_success:
            constraint = "Harness-generated commits must stay pushable back to the tracked remote branch"
            directive = "Review the pushed branch and linked PR context before enqueueing follow-up review work"
            not_tested = "Manual reviewer confirmation after pushing back to the tracked branch"

        return "\n".join(
            [
                f"Advance {task_title} through a {run.agent} harness run",
                "",
                *narrative,
                "",
                f"Constraint: {constraint}",
                "Confidence: medium",
                "Scope-risk: narrow",
                "Reversibility: clean",
                f"Directive: {directive}",
                f"Tested: {run.agent} harness run exited with status 0",
                f"Not-tested: {not_tested}",
                f"Related: task/{run.task_id}",
                f"Related: run/{run.id}",
            ]
        )

    async def _load_task_run(self, session: AsyncSession, run_id: str) -> TaskRun | None:
        stmt = (
            select(TaskRun)
            .where(TaskRun.id == run_id)
            .options(selectinload(TaskRun.task_rel))
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    def _apply_mock_run_result(self, run: TaskRun, started_at: float) -> None:
        run.status = "passed"
        run.check_passed = True
        run.changed_files = []
        run.duration_ms = max(1, int((asyncio.get_event_loop().time() - started_at) * 1000))
        run.raw_output = f"Mock run completed.\n{run.task}"
        run.result_summary = f"已完成 mock run：{run.task}"

    def _branch_name(self, run_id: str) -> str:
        return f"kam-run-{run_id}"

    def _task_execution_target(self, task_record: Task | None) -> _ExecutionTarget | None:
        metadata = task_record.metadata_ if task_record is not None and task_record.metadata_ else {}
        remote_url = metadata.get("executionRemoteUrl")
        ref = metadata.get("executionRef")
        if not isinstance(remote_url, str) or not remote_url.strip():
            return None
        if not isinstance(ref, str) or not ref.strip():
            return None
        head_sha = metadata.get("executionHeadSha")
        return _ExecutionTarget(
            remote_url=remote_url.strip(),
            ref=ref.strip(),
            head_sha=head_sha.strip() if isinstance(head_sha, str) and head_sha.strip() else None,
            push_on_success=bool(metadata.get("executionPushOnSuccess")),
        )

    def _build_source_context_artifact(self, metadata: dict[str, Any]) -> dict[str, Any] | None:
        source_kind = metadata.get("sourceKind")
        source_meta = metadata.get("sourceMeta")
        source_comments = metadata.get("sourceReviewComments")
        if not source_kind and not source_meta and not source_comments:
            return None
        payload = {
            "sourceKind": source_kind,
            "sourceRepo": metadata.get("sourceRepo"),
            "sourcePullNumber": metadata.get("sourcePullNumber"),
            "sourceMeta": source_meta if isinstance(source_meta, dict) else {},
            "sourceReviewComments": source_comments if isinstance(source_comments, list) else [],
        }
        return {
            "type": "source_context",
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
            "metadata": {"sourceKind": source_kind or "external"},
        }

    def _resolve_execution_start_point(self, repo_path: Path, execution_target: _ExecutionTarget) -> str:
        remote_name = self._ensure_remote(repo_path, execution_target.remote_url)
        try:
            self._git(repo_path, "fetch", "--prune", remote_name, execution_target.ref)
        except subprocess.CalledProcessError:
            if execution_target.head_sha is None:
                raise
            self._git(repo_path, "fetch", "--prune", remote_name, execution_target.head_sha)
        return self._git_output(repo_path, "rev-parse", "FETCH_HEAD").strip()

    def _ensure_remote(self, repo_path: Path, remote_url: str) -> str:
        origin_url = self._git_output(repo_path, "remote", "get-url", "origin").strip()
        if self._normalize_remote_url(origin_url) == self._normalize_remote_url(remote_url):
            return "origin"

        remote_name = f"kam-target-{hashlib.sha1(remote_url.encode('utf-8')).hexdigest()[:10]}"
        try:
            current_url = self._git_output(repo_path, "remote", "get-url", remote_name).strip()
            if self._normalize_remote_url(current_url) != self._normalize_remote_url(remote_url):
                self._git(repo_path, "remote", "set-url", remote_name, remote_url)
        except subprocess.CalledProcessError:
            self._git(repo_path, "remote", "add", remote_name, remote_url)
        return remote_name

    def _normalize_remote_url(self, url: str) -> str:
        normalized = url.strip().lower().replace(".git", "")
        if normalized.startswith("git@github.com:"):
            normalized = normalized.replace("git@github.com:", "https://github.com/")
        return normalized.rstrip("/")

    def _cleanup_worktree_branch(self, repo_path: Path, worktree_path: Path, run_id: str) -> None:
        self._git(repo_path, "worktree", "remove", str(worktree_path), "--force")
        self._git(repo_path, "branch", "-D", self._branch_name(run_id))

    def _git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _git_output(self, cwd: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout

    def _extract_output_text(self, line: str) -> str:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return line
        fragments = list(self._flatten_strings(payload))
        return " ".join(fragment for fragment in fragments if fragment)[:400]

    def _flatten_strings(self, value: Any) -> Iterable[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from self._flatten_strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from self._flatten_strings(item)

    def _capture_patch(self, worktree_path: Path | None) -> str:
        if worktree_path is None or not worktree_path.exists():
            return ""
        try:
            return self._git_output(worktree_path, "show", "--stat", "--patch", "HEAD")
        except subprocess.CalledProcessError:
            return ""

    def _build_artifacts(self, run: TaskRun, patch_output: str) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = [
            {"type": "task", "content": run.task, "metadata": {"agent": run.agent}},
            {"type": "stdout", "content": run.raw_output or "", "metadata": {"status": run.status}},
            {"type": "summary", "content": run.result_summary or "", "metadata": {"status": run.status}},
        ]
        artifacts = [*(_STATE.initial_artifacts.pop(run.id, [])), *artifacts]
        if run.changed_files:
            artifacts.append({"type": "changed_files", "content": json.dumps(run.changed_files, ensure_ascii=False)})
        if patch_output:
            artifacts.append({"type": "patch", "content": patch_output})
        return artifacts


async def wait_for_background_runs(timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        pending = [task for task in _STATE.tasks.values() if not task.done()]
        if not pending:
            break
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            break
        done, still_pending = await asyncio.wait(pending, timeout=remaining)
        if done:
            await asyncio.gather(*done, return_exceptions=True)
        if still_pending:
            for task in still_pending:
                task.cancel()
            await asyncio.gather(*still_pending, return_exceptions=True)
            break
    remaining = deadline - asyncio.get_event_loop().time()
    await wait_for_background_autodrive(timeout=max(0.0, remaining))


async def recover_interrupted_runs() -> int:
    async with async_session() as session:
        result = await session.execute(
            select(TaskRun)
            .where(TaskRun.status.in_(("pending", "running")))
            .options(selectinload(TaskRun.task_rel))
        )
        stale_runs = list(result.scalars())
        if not stale_runs:
            return 0

        recovered_count = 0
        for run in stale_runs:
            if run.id in _STATE.tasks and not _STATE.tasks[run.id].done():
                continue
            interruption_line = "Harness run interrupted before completion; marked failed during startup recovery."
            run.status = "failed"
            run.check_passed = False
            run.result_summary = "执行中断：服务重启前的 run 未完成，已标记为 failed。"
            run.raw_output = f"{run.raw_output or ''}\n{interruption_line}".strip()
            if run.task_rel is not None:
                run.task_rel.updated_at = now()
            recovered_count += 1

        if recovered_count:
            await session.commit()
        return recovered_count
