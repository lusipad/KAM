"""
Agent run 执行器
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.workspace import AgentRun, RunArtifact, TaskCard


def _read_text(path: Path, max_chars: int = 200_000) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content) > max_chars:
        return content[-max_chars:]
    return content


def _write_text(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


class RunExecutionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._threads: dict[str, threading.Thread] = {}

    def launch_run(self, run_id: str) -> bool:
        with self._lock:
            if run_id in self._threads:
                return False

        db = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if not run or run.status in {"queued", "running", "completed", "failed", "canceled"}:
                return False

            run.status = "queued"
            db.commit()
        finally:
            db.close()

        thread = threading.Thread(target=self._execute_run, args=(run_id,), daemon=True)
        with self._lock:
            self._threads[run_id] = thread
        thread.start()
        return True

    def cancel_run(self, run_id: str) -> bool:
        with self._lock:
            process = self._processes.get(run_id)
            thread = self._threads.get(run_id)

        if not process:
            if thread and thread.is_alive():
                thread.join(timeout=5)
                return True
            return False

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        if thread and thread.is_alive():
            thread.join(timeout=5)
        return True

    def _execute_run(self, run_id: str):
        db = SessionLocal()
        process: subprocess.Popen | None = None

        try:
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if not run:
                return

            if run.status == "canceled":
                self._refresh_task_status(db, task_id=str(run.task_id))
                db.commit()
                return

            task = db.query(TaskCard).filter(TaskCard.id == run.task_id).first()
            if not task:
                run.status = "failed"
                run.error_message = "关联任务不存在"
                db.commit()
                return

            execution = self._prepare_execution(db, run, task)
            run.status = "running"
            run.started_at = datetime.utcnow()
            run.metadata_ = {
                **(run.metadata_ or {}),
                "executionCwd": execution["execution_cwd"],
                "commandLine": execution["display_command"],
                "worktree": execution["worktree"],
            }
            self._ensure_artifact(
                db,
                run,
                "stdout",
                "stdout log",
                "",
                str(execution["stdout_path"]),
            )
            self._ensure_artifact(
                db,
                run,
                "stderr",
                "stderr log",
                "",
                str(execution["stderr_path"]),
            )
            db.commit()
            db.refresh(run)

            stdout_file = open(execution["stdout_path"], "w", encoding="utf-8")
            stderr_file = open(execution["stderr_path"], "w", encoding="utf-8")
            try:
                process = subprocess.Popen(
                    execution["command"],
                    cwd=execution["execution_cwd"],
                    stdout=stdout_file,
                    stderr=stderr_file,
                    stdin=subprocess.DEVNULL,
                    shell=execution["shell"],
                    text=True,
                )
                with self._lock:
                    self._processes[str(run.id)] = process
                run.metadata_ = {
                    **(run.metadata_ or {}),
                    "pid": process.pid,
                }
                db.commit()

                return_code = process.wait()
            finally:
                stdout_file.close()
                stderr_file.close()

            db.expire_all()
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if not run:
                return

            stdout_text = _read_text(execution["stdout_path"])
            stderr_text = _read_text(execution["stderr_path"])
            summary_text = self._resolve_summary(execution["summary_path"], stdout_text, stderr_text)

            self._ensure_artifact(
                db,
                run,
                "stdout",
                "stdout log",
                stdout_text,
                str(execution["stdout_path"]),
            )
            self._ensure_artifact(
                db,
                run,
                "stderr",
                "stderr log",
                stderr_text,
                str(execution["stderr_path"]),
            )
            self._ensure_artifact(
                db,
                run,
                "summary",
                f"{run.agent_name} summary",
                summary_text,
                str(execution["summary_path"]) if execution["summary_path"] else None,
            )
            git_summary = self._capture_git_artifacts(db, run, execution)
            if git_summary:
                run.metadata_ = {
                    **(run.metadata_ or {}),
                    "git": git_summary,
                }

            run.completed_at = run.completed_at or datetime.utcnow()
            if run.status == "canceled":
                run.error_message = run.error_message or "Run 已被用户取消"
            elif return_code == 0:
                run.status = "completed"
                run.error_message = None
            else:
                run.status = "failed"
                run.error_message = stderr_text or f"进程退出码 {return_code}"

            self._refresh_task_status(db, task_id=str(run.task_id))
            db.commit()
        except Exception as exc:
            if process is not None:
                with self._lock:
                    self._processes.pop(run_id, None)

            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                if run.status != "canceled":
                    run.status = "failed"
                    run.error_message = str(exc)
                run.completed_at = run.completed_at or datetime.utcnow()
                self._refresh_task_status(db, task_id=str(run.task_id))
                db.commit()
        finally:
            with self._lock:
                self._processes.pop(run_id, None)
                self._threads.pop(run_id, None)
            db.close()

    def _prepare_execution(self, db: Session, run: AgentRun, task: TaskCard) -> dict[str, Any]:
        run_dir = Path(run.workdir or settings.AGENT_WORKROOT).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

        execution_cwd = run_dir
        created_worktree: Path | None = None

        repo_path = self._resolve_repo_path(task)
        if repo_path:
            candidate_worktree = run_dir / "workspace"
            if self._create_git_worktree(repo_path, candidate_worktree):
                created_worktree = candidate_worktree
                execution_cwd = created_worktree
            else:
                execution_cwd = repo_path

        prompt_path = run_dir / "prompt.md"
        context_path = run_dir / "context.json"
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        summary_path = run_dir / "final.md"

        if run.command:
            command_text = (
                run.command
                .replace("{run_dir}", str(run_dir))
                .replace("{execution_cwd}", str(execution_cwd))
                .replace("{prompt_file}", str(prompt_path))
                .replace("{context_file}", str(context_path))
            )
            command, display_command = self._build_custom_command(command_text)
            return {
                "command": command,
                "display_command": display_command,
                "execution_cwd": str(execution_cwd),
                "run_dir": str(run_dir),
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "summary_path": summary_path,
                "shell": False,
                "worktree": str(created_worktree) if created_worktree else None,
            }

        if run.agent_type == "codex":
            executable = self._resolve_cli(settings.CODEX_CLI_PATH, "codex")
            command = [
                executable,
                "exec",
                "--skip-git-repo-check",
                "--full-auto",
                "-m",
                settings.CODEX_MODEL,
                "-c",
                f'model_reasoning_effort="{settings.CODEX_REASONING_EFFORT}"',
                "--output-last-message",
                str(summary_path),
                "-C",
                str(execution_cwd),
                run.prompt,
            ]
        elif run.agent_type in {"claude", "claude-code"}:
            executable = self._resolve_cli(settings.CLAUDE_CODE_CLI_PATH, "claude")
            command = [
                executable,
                "-p",
                "--permission-mode",
                "bypassPermissions",
                "--output-format",
                "text",
                run.prompt,
            ]
        else:
            raise RuntimeError(f"不支持的 agent type: {run.agent_type}，请提供 command 或使用 codex/claude-code")

        return {
            "command": command,
            "display_command": subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command),
            "execution_cwd": str(execution_cwd),
            "run_dir": str(run_dir),
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "summary_path": summary_path,
            "shell": False,
            "worktree": str(created_worktree) if created_worktree else None,
        }

    def _resolve_summary(self, summary_path: Path | None, stdout_text: str, stderr_text: str) -> str:
        if summary_path and summary_path.exists():
            summary = _read_text(summary_path)
            if summary.strip():
                return summary
        if stdout_text.strip():
            return stdout_text
        return stderr_text

    def _resolve_cli(self, configured: str, fallback: str) -> str:
        return shutil.which(configured) or shutil.which(fallback) or configured

    def _capture_git_artifacts(self, db: Session, run: AgentRun, execution: dict[str, Any]) -> dict[str, Any] | None:
        execution_cwd = Path(execution["execution_cwd"])
        run_dir = Path(execution["run_dir"])
        repo_root = self._get_git_root(execution_cwd)
        if not repo_root:
            return None

        status_output = self._git_output(execution_cwd, ["status", "--short", "--untracked-files=all"])
        diffstat_output = self._git_output(execution_cwd, ["diff", "--stat", "--find-renames", "HEAD"])
        patch_output = self._git_output(
            execution_cwd,
            ["diff", "--binary", "--no-ext-diff", "--find-renames", "HEAD"],
        )
        files = self._parse_git_status(status_output)
        summary = self._build_change_summary(repo_root, files, diffstat_output, execution_cwd)
        changes_path = run_dir / "git-changes.txt"
        patch_path = run_dir / "git.patch"

        _write_text(changes_path, summary)
        if patch_output.strip():
            _write_text(patch_path, patch_output)
        elif patch_path.exists():
            patch_path.unlink()

        counts = {
            "changed": len(files),
            "untracked": sum(1 for item in files if item["status"] == "??"),
            "trackedDiff": bool(patch_output.strip()),
        }
        change_artifact = self._ensure_artifact(
            db,
            run,
            "changes",
            "git changes",
            summary,
            str(changes_path),
        )
        change_artifact.metadata_ = {
            "repoRoot": str(repo_root),
            "executionCwd": str(execution_cwd),
            "files": files,
            **counts,
        }

        if patch_output.strip():
            patch_artifact = self._ensure_artifact(
                db,
                run,
                "patch",
                "git patch",
                patch_output,
                str(patch_path),
            )
            patch_artifact.metadata_ = {
                "repoRoot": str(repo_root),
                "executionCwd": str(execution_cwd),
                "files": [item["path"] for item in files],
                "changed": len(files),
            }

        return {
            "repoRoot": str(repo_root),
            "executionCwd": str(execution_cwd),
            "files": files,
            **counts,
        }

    def _git_output(self, cwd: Path, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(cwd), *args],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _parse_git_status(self, status_output: str) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        for raw_line in status_output.splitlines():
            line = raw_line.rstrip()
            if len(line) < 4:
                continue

            status = line[:2]
            path_text = line[3:] if len(line) > 2 and line[2] == " " else line[2:]
            original_path = ""
            if " -> " in path_text:
                original_path, path_text = path_text.split(" -> ", 1)

            files.append(
                {
                    "status": status,
                    "label": self._map_git_status(status),
                    "path": path_text,
                    "originalPath": original_path,
                }
            )
        return files

    def _map_git_status(self, status: str) -> str:
        status = status.strip()
        if status == "??":
            return "untracked"
        if "R" in status:
            return "renamed"
        if "A" in status:
            return "added"
        if "D" in status:
            return "deleted"
        if "M" in status:
            return "modified"
        if "C" in status:
            return "copied"
        return status or "unknown"

    def _build_change_summary(
        self,
        repo_root: Path,
        files: list[dict[str, str]],
        diffstat_output: str,
        execution_cwd: Path,
    ) -> str:
        lines = [
            f"Repo root: {repo_root}",
            f"Execution cwd: {execution_cwd}",
            f"Changed files: {len(files)}",
            "",
        ]

        if files:
            lines.append("Files:")
            for item in files:
                entry = f"- [{item['status']}] {item['path']}"
                if item["originalPath"]:
                    entry += f" (from {item['originalPath']})"
                lines.append(entry)
        else:
            lines.extend(
                [
                    "Files:",
                    "- No git changes detected.",
                ]
            )

        lines.extend(["", "Diff stat:"])
        if diffstat_output:
            lines.extend(diffstat_output.splitlines())
        else:
            lines.append("No tracked diff detected.")
        return "\n".join(lines)

    def _build_custom_command(self, command_text: str) -> tuple[list[str], str]:
        if os.name == "nt":
            executable = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            command = [
                executable,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command_text,
            ]
            return command, subprocess.list2cmdline(command)

        executable = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        flag = "-lc" if Path(executable).name == "bash" else "-c"
        command = [executable, flag, command_text]
        return command, " ".join(command)

    def _resolve_repo_path(self, task: TaskCard) -> Path | None:
        if not task.refs:
            return None

        for ref in task.refs:
            if ref.ref_type not in {"repo-path", "path", "workspace"}:
                continue
            candidate = Path(ref.value)
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return candidate
        return None

    def _create_git_worktree(self, repo_path: Path, worktree_path: Path) -> bool:
        repo_root = self._get_git_root(repo_path)
        if not repo_root:
            return False

        if worktree_path.exists():
            return True

        try:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(worktree_path)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return True
        except Exception:
            return False

    def _get_git_root(self, path: Path) -> Path | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            root = result.stdout.strip()
            return Path(root) if root else None
        except Exception:
            return None

    def _ensure_artifact(
        self,
        db: Session,
        run: AgentRun,
        artifact_type: str,
        title: str,
        content: str,
        path: str | None = None,
    ) -> RunArtifact:
        artifact = (
            db.query(RunArtifact)
            .filter(RunArtifact.run_id == run.id, RunArtifact.artifact_type == artifact_type)
            .first()
        )
        if artifact:
            artifact.title = title
            artifact.content = content
            artifact.path = path
            artifact.metadata_ = {
                **(artifact.metadata_ or {}),
                "updatedAt": datetime.utcnow().isoformat(),
            }
            return artifact

        artifact = RunArtifact(
            run_id=run.id,
            artifact_type=artifact_type,
            title=title,
            content=content,
            path=path,
        )
        db.add(artifact)
        return artifact

    def _refresh_task_status(self, db: Session, task_id: str):
        task = db.query(TaskCard).filter(TaskCard.id == task_id).first()
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


execution_manager = RunExecutionManager()
