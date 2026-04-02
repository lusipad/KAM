from __future__ import annotations

import asyncio
import json
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
from events import event_bus
from models import Project, Run, Thread, now
from services.artifact_store import ArtifactStore
from services.digest import DigestService


@dataclass
class _RunState:
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(settings.max_concurrent_runs))
    tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    initial_artifacts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


_STATE = _RunState()


class RunEngine:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_run(
        self,
        *,
        thread_id: str,
        agent: str,
        task: str,
        initial_artifacts: list[dict[str, Any]] | None = None,
    ) -> Run:
        run = Run(thread_id=thread_id, agent=agent, task=task, status="pending")
        self.db.add(run)
        thread = await self.db.get(Thread, thread_id)
        if thread is not None:
            thread.updated_at = now()
        await self.db.commit()
        await self.db.refresh(run)
        await self._publish(run, "run_queued", {"progress": "已排队"})
        if initial_artifacts:
            _STATE.initial_artifacts[run.id] = [dict(artifact) for artifact in initial_artifacts]
        if settings.is_test_env:
            await self._execute_run(run.id)
            await self.db.refresh(run)
            return run
        task_handle = asyncio.create_task(self._execute_run(run.id))
        _STATE.tasks[run.id] = task_handle
        return run

    async def retry_run(self, run_id: str) -> Run | None:
        run = await self.db.get(Run, run_id)
        if run is None:
            return None
        return await self.create_run(thread_id=run.thread_id, agent=run.agent, task=run.task)

    async def adopt_run(self, run_id: str) -> dict[str, Any]:
        run = await self.db.get(Run, run_id)
        if run is None:
            return {"ok": False, "error": "run_not_found"}
        if run.status != "passed":
            return {"ok": False, "error": "only_passed_runs_can_be_adopted"}
        if run.adopted_at is not None:
            return {"ok": True, "adoptedAt": run.adopted_at.isoformat()}

        thread = await self.db.get(Thread, run.thread_id)
        project = await self.db.get(Project, thread.project_id) if thread else None
        repo_path = Path(project.repo_path) if project and project.repo_path else None
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
        if thread is not None:
            thread.updated_at = now()
        await self.db.commit()
        await self._publish(run, "run_adopted", {"adoptedAt": run.adopted_at.isoformat()})
        return {"ok": True, "adoptedAt": run.adopted_at.isoformat()}

    async def _execute_run(self, run_id: str) -> None:
        async with _STATE.semaphore:
            try:
                async with async_session() as session:
                    run = await self._load_run(session, run_id)
                    if run is None:
                        return
                    thread = run.thread
                    project = thread.project if thread else None
                    run.status = "running"
                    if thread is not None:
                        thread.updated_at = now()
                    await session.commit()
                    await self._publish(run, "run_started", {"progress": "开始执行"})

                    started_at = asyncio.get_event_loop().time()
                    worktree_path, command = await self._prepare_execution(run, project)
                    patch_output = ""
                    if worktree_path is not None:
                        run.worktree_path = str(worktree_path)
                        await session.commit()

                    code, output = await self._run_command(run, command, worktree_path or settings.run_dir)
                    run.duration_ms = int((asyncio.get_event_loop().time() - started_at) * 1000)
                    run.raw_output = output[-20000:]

                    if code == 0:
                        changed_files = await self._finalize_success(run, project, worktree_path)
                        run.status = "passed"
                        run.changed_files = changed_files
                        run.check_passed = True
                        patch_output = self._capture_patch(worktree_path)
                    else:
                        run.status = "failed"
                        run.check_passed = False
                        run.changed_files = []

                    run.result_summary = await DigestService(session).summarize_run(run)
                    await ArtifactStore(session).replace_for_run(
                        run.id,
                        self._build_artifacts(run, patch_output),
                    )
                    if thread is not None:
                        thread.updated_at = now()
                    await session.commit()
                    await self._publish(
                        run,
                        "run_finished",
                        {
                            "status": run.status,
                            "summary": run.result_summary,
                            "changedFiles": run.changed_files or [],
                            "durationMs": run.duration_ms,
                        },
                    )
            except Exception as exc:
                async with async_session() as session:
                    run = await self._load_run(session, run_id)
                    if run is not None:
                        run.status = "failed"
                        run.check_passed = False
                        run.raw_output = f"{run.raw_output or ''}\n{type(exc).__name__}: {exc}".strip()
                        run.result_summary = f"执行失败：{type(exc).__name__}: {exc}"
                        await session.commit()
                        await self._publish(
                            run,
                            "run_finished",
                            {"status": run.status, "summary": run.result_summary, "changedFiles": [], "durationMs": run.duration_ms},
                        )
            finally:
                _STATE.tasks.pop(run_id, None)
                _STATE.initial_artifacts.pop(run_id, None)

    async def _prepare_execution(self, run: Run, project: Project | None) -> tuple[Path | None, list[str]]:
        repo_path = Path(project.repo_path).resolve() if project and project.repo_path else None
        if repo_path and repo_path.exists() and (repo_path / ".git").exists():
            worktree_path = settings.run_dir / run.id
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            branch = self._branch_name(run.id)
            self._git(repo_path, "worktree", "add", "-b", branch, str(worktree_path), "HEAD")
            command = self._build_command(run, worktree_path)
            return worktree_path, command

        scratch = settings.run_dir / run.id
        scratch.mkdir(parents=True, exist_ok=True)
        command = self._build_command(run, scratch)
        return None, command

    def _build_command(self, run: Run, cwd: Path) -> list[str]:
        if run.agent == "codex":
            return [
                settings.codex_path,
                "exec",
                "--json",
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
                "--cd",
                str(cwd),
                run.task,
            ]
        if run.agent == "claude-code":
            return [settings.claude_code_path, run.task]
        raise RuntimeError(f"unsupported_agent:{run.agent}")

    async def _run_command(self, run: Run, command: list[str], cwd: Path) -> tuple[int, str]:
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
            if extracted:
                await event_bus.publish("home", {"type": "run_progress", "message": extracted[:200]})
                await event_bus.publish(
                    f"thread:{run.thread_id}",
                    {"type": "run_progress", "runId": run.id, "threadId": run.thread_id, "message": extracted[:200]},
                )
        code = await process.wait()
        return code, "\n".join(output_lines)

    async def _finalize_success(self, run: Run, project: Project | None, worktree_path: Path | None) -> list[str]:
        if project is None or worktree_path is None or not worktree_path.exists():
            return []
        changed_files = self._git_output(worktree_path, "status", "--short")
        if not changed_files.strip():
            return []
        self._git(worktree_path, "config", "user.name", settings.git_user_name)
        self._git(worktree_path, "config", "user.email", settings.git_user_email)
        self._git(worktree_path, "add", "-A")
        self._git(worktree_path, "commit", "-m", f"KAM run {run.id}")
        committed_files = self._git_output(worktree_path, "show", "--pretty=", "--name-only", "HEAD")
        return [line.strip() for line in committed_files.splitlines() if line.strip()]

    async def _load_run(self, session: AsyncSession, run_id: str) -> Run | None:
        stmt = (
            select(Run)
            .where(Run.id == run_id)
            .options(selectinload(Run.thread).selectinload(Thread.project))
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def _publish(self, run: Run, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, "runId": run.id, "threadId": run.thread_id, **payload}
        await event_bus.publish(f"thread:{run.thread_id}", event)
        await event_bus.publish("home", event)

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

    def _build_artifacts(self, run: Run, patch_output: str) -> list[dict[str, Any]]:
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
