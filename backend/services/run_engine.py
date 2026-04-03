from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
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
from services.task_context import TaskContextService


@dataclass
class _RunState:
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(settings.max_concurrent_runs))
    tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    initial_artifacts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


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
                        return

                    worktree_path, command = await self._prepare_task_execution(run, task_record)
                    patch_output = ""
                    if worktree_path is not None:
                        run.worktree_path = str(worktree_path)
                        await session.commit()

                    code, output = await self._run_command(command, worktree_path or settings.run_dir)
                    run.duration_ms = int((asyncio.get_event_loop().time() - started_at) * 1000)
                    run.raw_output = output[-20000:]

                    repo_path = Path(task_record.repo_path).resolve() if task_record and task_record.repo_path else None
                    if code == 0:
                        changed_files = await self._finalize_success(run.id, repo_path, worktree_path)
                        run.status = "passed"
                        run.changed_files = changed_files
                        run.check_passed = True
                        patch_output = self._capture_patch(worktree_path)
                    else:
                        run.status = "failed"
                        run.check_passed = False
                        run.changed_files = []

                    run.result_summary = await DigestService(session).summarize_run(run)
                    await ArtifactStore(session).replace_for_run(run.id, self._build_artifacts(run, patch_output))
                    if task_record is not None:
                        task_record.updated_at = now()
                    await session.commit()
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
            finally:
                _STATE.tasks.pop(run_id, None)
                _STATE.initial_artifacts.pop(run_id, None)

    async def _prepare_task_execution(self, run: TaskRun, task_record: Task | None) -> tuple[Path | None, list[str]]:
        repo_path = Path(task_record.repo_path).resolve() if task_record and task_record.repo_path else None
        return await self._prepare_workspace(run.id, run.agent, run.task, repo_path)

    async def _prepare_workspace(
        self,
        run_id: str,
        agent: str,
        task: str,
        repo_path: Path | None,
    ) -> tuple[Path | None, list[str]]:
        if repo_path and repo_path.exists() and (repo_path / ".git").exists():
            worktree_path = settings.run_dir / run_id
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            branch = self._branch_name(run_id)
            self._git(repo_path, "worktree", "add", "-b", branch, str(worktree_path), "HEAD")
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

    async def _finalize_success(self, run_id: str, repo_path: Path | None, worktree_path: Path | None) -> list[str]:
        if repo_path is None or worktree_path is None or not worktree_path.exists():
            return []
        changed_files = self._git_output(worktree_path, "status", "--short")
        if not changed_files.strip():
            return []
        self._git(worktree_path, "config", "user.name", settings.git_user_name)
        self._git(worktree_path, "config", "user.email", settings.git_user_email)
        self._git(worktree_path, "add", "-A")
        self._git(worktree_path, "commit", "-m", f"KAM run {run_id}")
        committed_files = self._git_output(worktree_path, "show", "--pretty=", "--name-only", "HEAD")
        return [line.strip() for line in committed_files.splitlines() if line.strip()]

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
    pending = list(_STATE.tasks.values())
    if not pending:
        return
    done, still_pending = await asyncio.wait(pending, timeout=timeout)
    for task in still_pending:
        task.cancel()
    if still_pending:
        await asyncio.gather(*still_pending, return_exceptions=True)
    if done:
        await asyncio.gather(*done, return_exceptions=True)
