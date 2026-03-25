"""
KAM v2 Run Engine
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.conversation import Run, Thread, ThreadRunArtifact
from app.models.project import Project, ProjectResource


TERMINAL_RUN_STATUSES = {"passed", "failed", "cancelled"}
ACTIVE_RUN_STATUSES = {"pending", "running", "checking"}


def _read_text(path: Path, max_chars: int = 200_000) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content) > max_chars:
        return content[-max_chars:]
    return content


def _write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _tail_text(content: str, max_chars: int = 2_000) -> str:
    if len(content) <= max_chars:
        return content
    return content[-max_chars:]


def _slugify(text: str) -> str:
    value = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    return value or "artifact"


class V2RunExecutionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._cancel_flags: set[str] = set()

    def launch_run(self, run_id: str) -> bool:
        with self._lock:
            if run_id in self._threads:
                return False

        db = SessionLocal()
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if not run or run.status in {"running", "checking", "passed", "failed", "cancelled"}:
                return False
            run.status = "pending"
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
            self._cancel_flags.add(run_id)
            process = self._processes.get(run_id)
            thread = self._threads.get(run_id)

        if process and process.poll() is None:
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
            run = db.query(Run).filter(Run.id == run_id).first()
            if not run:
                return
            thread = db.query(Thread).filter(Thread.id == run.thread_id).first()
            if not thread:
                run.status = "failed"
                run.error = "关联线程不存在"
                run.completed_at = datetime.utcnow()
                db.commit()
                return

            run_root = Path(run.work_dir or settings.AGENT_WORKROOT).resolve()
            run_root.mkdir(parents=True, exist_ok=True)
            execution_cwd, worktree = self._resolve_execution_cwd(thread, run_root)

            base_prompt = self._artifact_content(db, run.id, "prompt") or ""
            base_context = self._artifact_content(db, run.id, "context") or "{}"
            checks = self._project_check_commands(thread.project)

            round_number = max(run.round or 1, 1)
            while True:
                if self._is_cancelled(run_id):
                    self._mark_cancelled(db, run_id, "Run 已取消")
                    return

                round_dir = run_root / f"round-{round_number:02d}"
                round_dir.mkdir(parents=True, exist_ok=True)
                prompt_text = base_prompt
                if round_number > 1:
                    feedback = self._latest_feedback(db, run.id)
                    if feedback:
                        prompt_text = f"{base_prompt}\n\n# Retry Feedback\n{feedback}"

                prompt_path = round_dir / "prompt.md"
                context_path = round_dir / "context.json"
                stdout_path = round_dir / "stdout.log"
                stderr_path = round_dir / "stderr.log"
                summary_path = round_dir / "final.md"

                _write_text(prompt_path, prompt_text)
                _write_text(context_path, base_context)
                self._record_artifact(db, run.id, "prompt", f"{run.agent} prompt", prompt_text, prompt_path, round_number)
                self._record_artifact(db, run.id, "context", "thread context", base_context, context_path, round_number)

                command, display_command = self._build_command(
                    run=run,
                    prompt_text=prompt_text,
                    run_root=run_root,
                    round_dir=round_dir,
                    execution_cwd=execution_cwd,
                    prompt_path=prompt_path,
                    context_path=context_path,
                    summary_path=summary_path,
                )

                run.status = "running"
                run.round = round_number
                run.metadata_ = {
                    **(run.metadata_ or {}),
                    "executionCwd": str(execution_cwd),
                    "commandLine": display_command,
                    "worktree": str(worktree) if worktree else None,
                    "startedAt": (run.metadata_ or {}).get("startedAt") or datetime.utcnow().isoformat(),
                }
                if round_number == 1:
                    run.completed_at = None
                db.commit()

                with open(stdout_path, "w", encoding="utf-8") as stdout_file, open(stderr_path, "w", encoding="utf-8") as stderr_file:
                    process = subprocess.Popen(
                        command,
                        cwd=str(execution_cwd),
                        stdout=stdout_file,
                        stderr=stderr_file,
                        stdin=subprocess.DEVNULL,
                        text=True,
                    )
                    with self._lock:
                        self._processes[run_id] = process
                    run.metadata_ = {
                        **(run.metadata_ or {}),
                        "pid": process.pid,
                    }
                    db.commit()
                    return_code = process.wait()

                stdout_text = _read_text(stdout_path)
                stderr_text = _read_text(stderr_path)
                summary_text = self._resolve_summary(summary_path, stdout_text, stderr_text)

                self._record_artifact(db, run.id, "stdout", f"stdout round {round_number}", stdout_text, stdout_path, round_number)
                self._record_artifact(db, run.id, "stderr", f"stderr round {round_number}", stderr_text, stderr_path, round_number)
                self._record_artifact(db, run.id, "summary", f"summary round {round_number}", summary_text, summary_path, round_number)
                git_summary = self._capture_git_artifacts(db, run.id, round_number, execution_cwd, round_dir)
                if git_summary:
                    run.metadata_ = {
                        **(run.metadata_ or {}),
                        "git": git_summary,
                    }
                db.commit()

                if self._is_cancelled(run_id):
                    self._mark_cancelled(db, run_id, "Run 已取消")
                    return

                if return_code != 0:
                    run.status = "failed"
                    run.error = stderr_text or f"进程退出码 {return_code}"
                    run.completed_at = datetime.utcnow()
                    db.commit()
                    return

                run.status = "checking"
                db.commit()

                check_results = self._execute_checks(
                    run_id=run.id,
                    round_number=round_number,
                    checks=checks,
                    execution_cwd=execution_cwd,
                    run_root=run_root,
                    round_dir=round_dir,
                    thread=thread,
                )
                all_passed = all(item["passed"] for item in check_results) if check_results else True
                self._record_artifact(
                    db,
                    run.id,
                    "check_result",
                    f"check results round {round_number}",
                    json.dumps(check_results, ensure_ascii=False, indent=2),
                    round_dir / "check-results.json",
                    round_number,
                    metadata={"passed": all_passed},
                )
                db.commit()

                if all_passed:
                    run.status = "passed"
                    run.error = None
                    run.completed_at = datetime.utcnow()
                    run.duration_ms = self._duration_ms(run)
                    db.commit()
                    return

                if round_number >= (run.max_rounds or 1):
                    run.status = "failed"
                    run.error = self._build_retry_feedback(check_results)
                    run.completed_at = datetime.utcnow()
                    run.duration_ms = self._duration_ms(run)
                    db.commit()
                    return

                feedback_text = self._build_retry_feedback(check_results)
                self._record_artifact(
                    db,
                    run.id,
                    "feedback",
                    f"retry feedback round {round_number}",
                    feedback_text,
                    round_dir / "retry-feedback.txt",
                    round_number,
                )
                run.metadata_ = {
                    **(run.metadata_ or {}),
                    "lastFailedRound": round_number,
                    "lastFeedback": feedback_text,
                }
                run.status = "pending"
                db.commit()
                round_number += 1
        except Exception as exc:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run and run.status != "cancelled":
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = datetime.utcnow()
                run.duration_ms = self._duration_ms(run)
                db.commit()
        finally:
            with self._lock:
                self._processes.pop(run_id, None)
                self._threads.pop(run_id, None)
                self._cancel_flags.discard(run_id)
            db.close()

    def _resolve_execution_cwd(self, thread: Thread, run_root: Path) -> tuple[Path, Path | None]:
        repo_path = self._resolve_repo_path(thread.project)
        if not repo_path:
            return run_root, None

        candidate_worktree = run_root / "workspace"
        if self._create_git_worktree(repo_path, candidate_worktree):
            return candidate_worktree, candidate_worktree
        return repo_path, None

    def _resolve_repo_path(self, project: Project | None) -> Path | None:
        if not project:
            return None
        if project.repo_path:
            candidate = Path(project.repo_path)
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return candidate.resolve()

        for resource in project.resources or []:
            if resource.resource_type not in {"repo-path", "path", "workspace"}:
                continue
            candidate = Path(resource.uri)
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return candidate.resolve()
        return None

    def _project_check_commands(self, project: Project | None) -> list[dict[str, str]]:
        if not project or not project.check_commands:
            return []

        commands: list[dict[str, str]] = []
        for index, raw in enumerate(project.check_commands, start=1):
            if isinstance(raw, dict):
                label = str(raw.get("label") or f"check-{index}")
                command = str(raw.get("command") or "").strip()
            else:
                label = f"check-{index}"
                command = str(raw).strip()
            if command:
                commands.append({"label": label, "command": command})
        return commands

    def _build_command(
        self,
        *,
        run: Run,
        prompt_text: str,
        run_root: Path,
        round_dir: Path,
        execution_cwd: Path,
        prompt_path: Path,
        context_path: Path,
        summary_path: Path,
    ) -> tuple[list[str], str]:
        if run.command:
            command_text = (
                run.command
                .replace("{run_dir}", str(run_root))
                .replace("{round_dir}", str(round_dir))
                .replace("{execution_cwd}", str(execution_cwd))
                .replace("{prompt_file}", str(prompt_path))
                .replace("{context_file}", str(context_path))
                .replace("{summary_file}", str(summary_path))
                .replace("{round}", str(run.round or 1))
            )
            return self._build_custom_command(command_text)

        if run.agent == "codex":
            executable = self._resolve_cli(settings.CODEX_CLI_PATH, "codex")
            command = [
                executable,
                "exec",
                "--skip-git-repo-check",
                "--full-auto",
                "-m",
                run.model or settings.CODEX_MODEL,
                "-c",
                f'model_reasoning_effort="{run.reasoning_effort or settings.CODEX_REASONING_EFFORT}"',
                "--output-last-message",
                str(summary_path),
                "-C",
                str(execution_cwd),
                prompt_text,
            ]
            return command, (subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command))

        if run.agent in {"claude", "claude-code"}:
            executable = self._resolve_cli(settings.CLAUDE_CODE_CLI_PATH, "claude")
            command = [
                executable,
                "-p",
                "--permission-mode",
                "bypassPermissions",
                "--output-format",
                "text",
                prompt_text,
            ]
            return command, (subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command))

        raise RuntimeError(f"不支持的 agent: {run.agent}")

    def _execute_checks(
        self,
        *,
        run_id: str,
        round_number: int,
        checks: list[dict[str, str]],
        execution_cwd: Path,
        run_root: Path,
        round_dir: Path,
        thread: Thread,
    ) -> list[dict[str, Any]]:
        if not checks:
            return []

        results: list[dict[str, Any]] = []
        checks_dir = round_dir / "checks"
        checks_dir.mkdir(parents=True, exist_ok=True)
        repo_path = self._resolve_repo_path(thread.project) or execution_cwd

        for index, check in enumerate(checks, start=1):
            template = check["command"]
            resolved_command = (
                template.replace("{repo_path}", str(repo_path))
                .replace("{execution_cwd}", str(execution_cwd))
                .replace("{run_dir}", str(run_root))
                .replace("{round_dir}", str(round_dir))
                .replace("{thread_id}", str(thread.id))
                .replace("{project_id}", str(thread.project_id))
            )
            stdout_path = checks_dir / f"{index:02d}-{_slugify(check['label'])}.stdout.log"
            stderr_path = checks_dir / f"{index:02d}-{_slugify(check['label'])}.stderr.log"

            started_at = time.perf_counter()
            try:
                command, display_command = self._build_custom_command(resolved_command)
                completed = subprocess.run(
                    command,
                    cwd=str(execution_cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                stdout_text = completed.stdout or ""
                stderr_text = completed.stderr or ""
                exit_code = completed.returncode
            except Exception as exc:
                display_command = resolved_command
                stdout_text = ""
                stderr_text = str(exc)
                exit_code = -1

            duration_ms = int((time.perf_counter() - started_at) * 1000)
            _write_text(stdout_path, stdout_text)
            _write_text(stderr_path, stderr_text)

            results.append(
                {
                    "label": check["label"],
                    "command": template,
                    "resolvedCommand": display_command,
                    "passed": exit_code == 0,
                    "exitCode": exit_code,
                    "durationMs": duration_ms,
                    "stdoutPath": str(stdout_path),
                    "stderrPath": str(stderr_path),
                    "stdoutPreview": _tail_text(stdout_text),
                    "stderrPreview": _tail_text(stderr_text),
                }
            )

        return results

    def _build_retry_feedback(self, check_results: list[dict[str, Any]]) -> str:
        failed = [item for item in check_results if not item["passed"]]
        if not failed:
            return "检查未通过，请结合日志继续修复。"

        lines = ["以下检查失败，请修复后继续执行："]
        for item in failed:
            lines.append(f"- {item['label']}: exit={item['exitCode']}")
            preview = item.get("stderrPreview") or item.get("stdoutPreview") or ""
            if preview:
                lines.append(preview.strip())
        return "\n".join(lines)

    def _latest_feedback(self, db, run_id: str) -> str:
        artifact = (
            db.query(ThreadRunArtifact)
            .filter(ThreadRunArtifact.run_id == run_id, ThreadRunArtifact.artifact_type == "feedback")
            .order_by(ThreadRunArtifact.created_at.desc())
            .first()
        )
        return artifact.content if artifact else ""

    def _artifact_content(self, db, run_id: str, artifact_type: str) -> str:
        artifact = (
            db.query(ThreadRunArtifact)
            .filter(ThreadRunArtifact.run_id == run_id, ThreadRunArtifact.artifact_type == artifact_type)
            .order_by(ThreadRunArtifact.created_at.asc())
            .first()
        )
        return artifact.content if artifact else ""

    def _record_artifact(
        self,
        db,
        run_id: str,
        artifact_type: str,
        title: str,
        content: str,
        path: Path | None,
        round_number: int,
        metadata: dict[str, Any] | None = None,
    ) -> ThreadRunArtifact:
        artifact = ThreadRunArtifact(
            run_id=run_id,
            artifact_type=artifact_type,
            title=title,
            content=content,
            path=str(path) if path else None,
            round=round_number,
            metadata_=metadata or {},
        )
        db.add(artifact)
        return artifact

    def _resolve_summary(self, summary_path: Path | None, stdout_text: str, stderr_text: str) -> str:
        if summary_path and summary_path.exists():
            summary = _read_text(summary_path)
            if summary.strip():
                return summary
        if stdout_text.strip():
            return stdout_text
        return stderr_text

    def _capture_git_artifacts(self, db, run_id: str, round_number: int, execution_cwd: Path, round_dir: Path) -> dict[str, Any] | None:
        repo_root = self._get_git_root(execution_cwd)
        if not repo_root:
            return None

        status_output = self._git_output(execution_cwd, ["status", "--short", "--untracked-files=all"])
        diffstat_output = self._git_output(execution_cwd, ["diff", "--stat", "--find-renames", "HEAD"])
        patch_output = self._git_output(execution_cwd, ["diff", "--binary", "--no-ext-diff", "--find-renames", "HEAD"])
        files = self._parse_git_status(status_output)
        summary = self._build_change_summary(repo_root, files, diffstat_output, execution_cwd)
        changes_path = round_dir / "git-changes.txt"
        patch_path = round_dir / "git.patch"
        _write_text(changes_path, summary)
        if patch_output.strip():
            _write_text(patch_path, patch_output)

        counts = {
            "changed": len(files),
            "untracked": sum(1 for item in files if item["status"] == "??"),
            "trackedDiff": bool(patch_output.strip()),
        }
        self._record_artifact(
            db,
            run_id,
            "changes",
            f"git changes round {round_number}",
            summary,
            changes_path,
            round_number,
            metadata={
                "repoRoot": str(repo_root),
                "executionCwd": str(execution_cwd),
                "files": files,
                **counts,
            },
        )
        if patch_output.strip():
            self._record_artifact(
                db,
                run_id,
                "patch",
                f"git patch round {round_number}",
                patch_output,
                patch_path,
                round_number,
                metadata={
                    "repoRoot": str(repo_root),
                    "executionCwd": str(execution_cwd),
                    "files": [item["path"] for item in files],
                    "changed": len(files),
                },
            )

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
        value = status.strip()
        if value == "??":
            return "untracked"
        if "R" in value:
            return "renamed"
        if "A" in value:
            return "added"
        if "D" in value:
            return "deleted"
        if "M" in value:
            return "modified"
        if "C" in value:
            return "copied"
        return value or "unknown"

    def _build_change_summary(self, repo_root: Path, files: list[dict[str, str]], diffstat_output: str, execution_cwd: Path) -> str:
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
            lines.extend(["Files:", "- No git changes detected."])
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

    def _resolve_cli(self, configured: str, fallback: str) -> str:
        return shutil.which(configured) or shutil.which(fallback) or configured

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

    def _is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancel_flags

    def _mark_cancelled(self, db, run_id: str, message: str):
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return
        run.status = "cancelled"
        run.error = message
        run.completed_at = datetime.utcnow()
        run.duration_ms = self._duration_ms(run)
        db.commit()

    def _duration_ms(self, run: Run | None) -> int | None:
        if not run or not run.completed_at:
            return None
        started_at_raw = (run.metadata_ or {}).get("startedAt")
        if not started_at_raw:
            return None
        try:
            started_at = datetime.fromisoformat(started_at_raw)
        except Exception:
            return None
        return int((run.completed_at - started_at).total_seconds() * 1000)


run_engine = V2RunExecutionManager()
