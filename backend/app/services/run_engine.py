"""
KAM v2 Run Engine
"""
from __future__ import annotations

import hashlib
import json
import os
from queue import Empty, Queue
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.events import event_bus
from app.db.base import SessionLocal
from app.models.conversation import Message, Run, Thread, ThreadRunArtifact
from app.models.project import Project, ProjectResource
from app.services.anthropic_service import AnthropicService
from app.services.memory_service import MemoryService
from app.services.thread_service import ThreadService


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
        self._anthropic = AnthropicService()
        self._claude_help_text: str | None = None

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
            execution_cwd, worktree, worktree_branch = self._resolve_execution_cwd(thread, run_root, run_id)
            git_baseline = self._capture_git_baseline(execution_cwd)

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
                    base_context=base_context,
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
                    "worktreeBranch": worktree_branch,
                    "startedAt": (run.metadata_ or {}).get("startedAt") or datetime.utcnow().isoformat(),
                }
                if round_number == 1:
                    run.completed_at = None
                self._record_thread_event(
                    db,
                    run,
                    f"{run.agent} 第 {round_number} 轮开始执行",
                    "run-started",
                    metadata={"commandLine": display_command},
                )
                db.commit()
                self._publish_run_event(
                    run,
                    "run-progress",
                    stdoutTail="",
                    stderrTail="",
                    stage="started",
                )

                return_code, stdout_text, stderr_text, stream_summary, pid = self._execute_process_streaming(
                    run=run,
                    run_id=run_id,
                    command=command,
                    execution_cwd=execution_cwd,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )
                run.metadata_ = {
                    **(run.metadata_ or {}),
                    "pid": pid,
                }
                db.commit()

                summary_text = self._resolve_summary(summary_path, stdout_text, stderr_text, stream_summary)

                self._record_artifact(db, run.id, "stdout", f"stdout round {round_number}", stdout_text, stdout_path, round_number)
                self._record_artifact(db, run.id, "stderr", f"stderr round {round_number}", stderr_text, stderr_path, round_number)
                self._record_artifact(db, run.id, "summary", f"summary round {round_number}", summary_text, summary_path, round_number)
                git_summary = self._capture_git_artifacts(
                    db,
                    run.id,
                    round_number,
                    execution_cwd,
                    round_dir,
                    git_baseline=git_baseline,
                )
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
                    self._mark_terminal_run(
                        db,
                        run,
                        status="failed",
                        event_type="run-failed",
                        content=f"{run.agent} 第 {round_number} 轮执行失败",
                        error=stderr_text or f"进程退出码 {return_code}",
                        metadata={"errorPreview": _tail_text(stderr_text or "", 600)},
                    )
                    self._schedule_run_digest(run.id, str(run.thread_id), "failed")
                    return

                run.status = "checking"
                self._record_thread_event(
                    db,
                    run,
                    f"{run.agent} 第 {round_number} 轮进入检查",
                    "run-checking",
                )
                db.commit()
                self._publish_run_event(run, "run-progress", stage="checking", stdoutTail=_tail_text(stdout_text, 400))

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
                    self._capture_project_learning(db, run, summary_text)
                    self._mark_terminal_run(
                        db,
                        run,
                        status="passed",
                        event_type="run-passed",
                        content=f"{run.agent} 第 {round_number} 轮检查通过",
                        metadata={"durationMs": self._duration_ms(run)},
                    )
                    self._schedule_run_digest(run.id, str(run.thread_id), "passed")
                    return

                if round_number >= (run.max_rounds or 1):
                    failure_feedback = self._build_retry_feedback(check_results)
                    self._mark_terminal_run(
                        db,
                        run,
                        status="failed",
                        event_type="run-failed",
                        content=f"{run.agent} 在第 {round_number} 轮后仍未通过检查",
                        error=failure_feedback,
                        metadata={"errorPreview": _tail_text(failure_feedback, 600)},
                    )
                    self._schedule_run_digest(run.id, str(run.thread_id), "failed")
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
                self._record_thread_event(
                    db,
                    run,
                    f"{run.agent} 第 {round_number} 轮未通过，准备重试",
                    "run-retrying",
                    metadata={"nextRound": round_number + 1, "errorPreview": _tail_text(feedback_text, 600)},
                )
                db.commit()
                self._publish_run_event(
                    run,
                    "run-progress",
                    stage="retrying",
                    stdoutTail=_tail_text(stdout_text, 400),
                    stderrTail=_tail_text(feedback_text, 400),
                )
                round_number += 1
        except Exception as exc:
            db.rollback()
            run = db.query(Run).filter(Run.id == run_id).first()
            if run and run.status != "cancelled":
                self._mark_terminal_run(
                    db,
                    run,
                    status="failed",
                    event_type="run-failed",
                    content=f"{run.agent} 执行异常终止",
                    error=str(exc),
                    metadata={"errorPreview": _tail_text(str(exc), 600)},
                )
                self._schedule_run_digest(run.id, str(run.thread_id), "failed")
        finally:
            final_db = SessionLocal()
            try:
                final_run = final_db.query(Run).filter(Run.id == run_id).first()
                if final_run and final_run.status in {"failed", "cancelled"}:
                    self._cleanup_run_worktree(final_run)
            finally:
                final_db.close()
            with self._lock:
                self._processes.pop(run_id, None)
                self._threads.pop(run_id, None)
                self._cancel_flags.discard(run_id)
            db.close()

    def _resolve_execution_cwd(self, thread: Thread, run_root: Path, run_id: str) -> tuple[Path, Path | None, str | None]:
        repo_path = self._resolve_repo_path(thread.project)
        if not repo_path:
            return run_root, None, None

        candidate_worktree = run_root / "workspace"
        worktree_branch = f"kam-run-{str(run_id).replace('-', '')[:12]}"
        if self._create_git_worktree(repo_path, candidate_worktree, worktree_branch):
            return candidate_worktree, candidate_worktree, worktree_branch
        return repo_path, None, None

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
        base_context: str,
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
            self._prepare_codex_context(
                execution_cwd=execution_cwd,
                skill_instructions=str((run.metadata_ or {}).get("skillInstructions") or "").strip() or None,
            )
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
            prompt_with_context = f"# Context\n\n{base_context}\n\n# Task\n\n{prompt_text}"
            command = [
                executable,
                "-p",
                "--dangerously-skip-permissions",
                "--output-format",
                "stream-json",
            ]
            if self._claude_supports_flag("--cwd"):
                command.extend(["--cwd", str(execution_cwd)])
            command.append(prompt_with_context)
            return command, (subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command))

        raise RuntimeError(f"不支持的 agent: {run.agent}")

    def _execute_process_streaming(
        self,
        *,
        run: Run,
        run_id: str,
        command: list[str],
        execution_cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
    ) -> tuple[int, str, str, str, int | None]:
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        assistant_parts: list[str] = []
        stream_queue: Queue[tuple[str, str | None]] = Queue()

        with open(stdout_path, "w", encoding="utf-8") as stdout_file, open(stderr_path, "w", encoding="utf-8") as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=str(execution_cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            with self._lock:
                self._processes[run_id] = process

            def reader(pipe, stream_name: str, sink):
                try:
                    if pipe is None:
                        return
                    for line in iter(pipe.readline, ""):
                        sink.write(line)
                        sink.flush()
                        stream_queue.put((stream_name, line))
                finally:
                    if pipe is not None:
                        pipe.close()
                    stream_queue.put((stream_name, None))

            stdout_thread = threading.Thread(target=reader, args=(process.stdout, "stdout", stdout_file), daemon=True)
            stderr_thread = threading.Thread(target=reader, args=(process.stderr, "stderr", stderr_file), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            closed_streams = 0
            last_publish = 0.0
            while closed_streams < 2:
                if self._is_cancelled(run_id) and process.poll() is None:
                    process.terminate()
                try:
                    stream_name, line = stream_queue.get(timeout=0.25)
                except Empty:
                    if process.poll() is not None and not stdout_thread.is_alive() and not stderr_thread.is_alive():
                        break
                    continue

                if line is None:
                    closed_streams += 1
                    continue

                if stream_name == "stdout":
                    stdout_parts.append(line)
                    assistant_parts.extend(self._extract_stream_json_text(line))
                else:
                    stderr_parts.append(line)

                now = time.time()
                if now - last_publish >= 0.2:
                    self._publish_run_event(
                        run,
                        "run-progress",
                        stage="streaming",
                        stdoutTail=_tail_text("".join(stdout_parts), 400),
                        stderrTail=_tail_text("".join(stderr_parts), 400),
                    )
                    last_publish = now

            return_code = process.wait()
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

        stdout_text = "".join(stdout_parts)
        stderr_text = "".join(stderr_parts)
        return return_code, stdout_text, stderr_text, "".join(assistant_parts).strip(), process.pid

    def _extract_stream_json_text(self, line: str) -> list[str]:
        try:
            payload = json.loads(line)
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        collected: list[str] = []
        for key in ("text", "delta", "message", "content"):
            value = payload.get(key)
            if isinstance(value, str):
                collected.append(value)
        delta = payload.get("delta")
        if isinstance(delta, dict):
            text = delta.get("text")
            if isinstance(text, str):
                collected.append(text)
        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        collected.append(text)
        return collected

    def _publish_run_event(self, run: Run | None, event_type: str, **payload: Any):
        if not run:
            return
        event = {
            "type": event_type,
            "runId": str(run.id),
            "threadId": str(run.thread_id),
            "status": run.status,
            "round": run.round,
            **payload,
        }
        event_bus.publish(f"thread:{run.thread_id}", event)
        event_bus.publish(f"run:{run.id}", event)

    def _mark_terminal_run(
        self,
        db,
        run: Run,
        *,
        status: str,
        event_type: str,
        content: str,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        run.status = status
        run.error = error
        run.completed_at = datetime.utcnow()
        run.duration_ms = self._duration_ms(run)
        event_metadata = {
            **(metadata or {}),
            "durationMs": run.duration_ms,
            "errorPreview": _tail_text(error or "", 600) if error else (metadata or {}).get("errorPreview"),
        }
        self._record_thread_event(db, run, content, event_type, metadata=event_metadata)
        db.commit()
        self._publish_run_event(
            run,
            "thread-done" if status in TERMINAL_RUN_STATUSES else "run-progress",
            stage=status,
            stdoutTail="",
            stderrTail=_tail_text(error or "", 400),
        )

    def _schedule_run_digest(self, run_id: str, thread_id: str, status: str):
        worker = threading.Thread(
            target=self._do_run_digest,
            args=(run_id, thread_id, status),
            daemon=True,
        )
        worker.start()

    def _do_run_digest(self, run_id: str, thread_id: str, status: str):
        db = SessionLocal()
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if not run:
                return

            digest = self._call_digest_llm(
                status=status,
                agent=run.agent,
                rounds=run.round or 1,
                duration_ms=run.duration_ms,
                summary=self._artifact_content(db, run_id, "summary"),
                check_results=self._artifact_content(db, run_id, "check_result"),
                changes=self._artifact_content(db, run_id, "changes"),
                error=run.error or "",
            )
            if not digest.strip():
                return

            message = ThreadService(db).create_message(
                thread_id,
                {
                    "role": "assistant",
                    "content": digest,
                    "metadata": {
                        "generatedBy": "run-digest",
                        "runId": run_id,
                        "runStatus": status,
                    },
                },
            )
            if message:
                event_bus.publish(
                    f"thread:{thread_id}",
                    {
                        "type": "thread-updated",
                        "runId": run_id,
                        "threadId": thread_id,
                        "status": status,
                    },
                )
        finally:
            db.close()

    def _call_digest_llm(
        self,
        *,
        status: str,
        agent: str,
        rounds: int,
        duration_ms: int | None,
        summary: str,
        check_results: str,
        changes: str,
        error: str,
    ) -> str:
        digest_changes = self._build_digest_change_preview(changes)
        if self._anthropic.enabled:
            prompt = self._anthropic.generate_text_sync(
                system=(
                    "你是 KAM 的 run 结果摘要器。"
                    "基于执行摘要、检查结果和变更列表，输出 1 到 4 句话，直接说明完成了什么、失败原因或下一步。"
                    "不要罗列原始 JSON，不要加标题。"
                ),
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "status": status,
                                "agent": agent,
                                "rounds": rounds,
                                "durationMs": duration_ms,
                                "summary": summary[:4000],
                                "checkResults": check_results[:4000],
                                "changes": digest_changes[:1200],
                                "error": error[:2000],
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
                max_tokens=280,
                model=settings.ANTHROPIC_SMALL_MODEL,
            )
            if prompt.strip():
                return prompt.strip()
        return self._build_digest_fallback(
            status=status,
            agent=agent,
            rounds=rounds,
            duration_ms=duration_ms,
            summary=summary,
            check_results=check_results,
            changes=changes,
            error=error,
        )

    def _build_digest_fallback(
        self,
        *,
        status: str,
        agent: str,
        rounds: int,
        duration_ms: int | None,
        summary: str,
        check_results: str,
        changes: str,
        error: str,
    ) -> str:
        duration_text = f"，耗时 {duration_ms}ms" if duration_ms else ""
        clean_summary = " ".join((summary or "").strip().split())
        change_preview = self._build_digest_change_preview(changes)
        has_checks = self._has_recorded_checks(check_results)
        if status == "passed":
            parts = [f"{agent} 已在第 {rounds} 轮完成本次执行{duration_text}。"]
            if clean_summary:
                parts.append(clean_summary[:220])
            if change_preview:
                parts.append(change_preview)
            if has_checks:
                parts.append("相关检查已执行，可在 Run 详情查看结果。")
            return " ".join(parts)

        failure = " ".join((error or clean_summary or "").strip().split())
        parts = [f"{agent} 本次执行失败，停止在第 {rounds} 轮{duration_text}。"]
        if failure:
            parts.append(failure[:220])
        if has_checks:
            parts.append("建议先查看失败检查和 stderr，再决定是否重试。")
        return " ".join(parts)

    def _build_digest_change_preview(self, changes: str) -> str:
        files: list[str] = []
        in_files = False
        for raw_line in (changes or "").splitlines():
            line = raw_line.strip()
            if line == "Files:":
                in_files = True
                continue
            if line == "Diff stat:":
                break
            if not in_files or not line.startswith("- ["):
                continue

            status_end = line.find("] ")
            if status_end <= 3:
                continue
            status = line[3:status_end]
            path_text = line[status_end + 2:]
            original_path = ""
            rename_marker = " (from "
            if path_text.endswith(")") and rename_marker in path_text:
                path_text, original_path = path_text[:-1].split(rename_marker, 1)

            label = self._digest_change_label(status)
            entry = f"{label}{path_text}"
            if original_path:
                entry = f"{entry}（原 {original_path}）"
            files.append(entry)
            if len(files) >= 3:
                break

        if files:
            return f"涉及文件：{'，'.join(files)}。"
        return ""

    def _digest_change_label(self, status: str) -> str:
        value = status.strip()
        if value == "??" or "A" in value:
            return "新增 "
        if "R" in value:
            return "重命名 "
        if "D" in value:
            return "删除 "
        if "M" in value:
            return "修改 "
        if "C" in value:
            return "复制 "
        return ""

    def _has_recorded_checks(self, check_results: str) -> bool:
        try:
            parsed = json.loads(check_results or "[]")
        except Exception:
            return bool((check_results or "").strip())
        return isinstance(parsed, list) and bool(parsed)

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

    def _resolve_summary(self, summary_path: Path | None, stdout_text: str, stderr_text: str, stream_summary: str = "") -> str:
        if summary_path and summary_path.exists():
            summary = _read_text(summary_path)
            if summary.strip():
                return summary
        if stream_summary.strip():
            return stream_summary
        if stdout_text.strip():
            return stdout_text
        return stderr_text

    def _capture_git_baseline(self, execution_cwd: Path) -> dict[str, Any] | None:
        repo_root = self._get_git_root(execution_cwd)
        if not repo_root:
            return None

        status_output = self._git_output(repo_root, ["status", "--short", "--untracked-files=all"])
        files = self._parse_git_status(status_output)
        baseline_files = {
            item["path"]: {
                "path": item["path"],
                "originalPath": item["originalPath"],
                "status": item["status"],
                "fingerprint": self._fingerprint_repo_file(repo_root, item["path"]),
            }
            for item in files
        }
        return {
            "repoRoot": str(repo_root),
            "files": baseline_files,
        }

    def _capture_git_artifacts(
        self,
        db,
        run_id: str,
        round_number: int,
        execution_cwd: Path,
        round_dir: Path,
        *,
        git_baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        repo_root = self._get_git_root(execution_cwd)
        if not repo_root:
            return None

        status_output = self._git_output(repo_root, ["status", "--short", "--untracked-files=all"])
        files = self._filter_git_status_entries(
            repo_root,
            self._parse_git_status(status_output),
            git_baseline,
        )
        tracked_paths = self._tracked_git_paths(files)
        diffstat_output = self._git_diff_output(
            repo_root,
            ["diff", "--stat", "--find-renames", "HEAD"],
            tracked_paths,
        )
        patch_output = self._git_diff_output(
            repo_root,
            ["diff", "--binary", "--no-ext-diff", "--find-renames", "HEAD"],
            tracked_paths,
        )
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

    def _filter_git_status_entries(
        self,
        repo_root: Path,
        files: list[dict[str, str]],
        git_baseline: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        if not git_baseline:
            return files
        baseline_root = Path(str(git_baseline.get("repoRoot") or "")).resolve()
        if baseline_root != repo_root.resolve():
            return files
        baseline_files = git_baseline.get("files")
        if not isinstance(baseline_files, dict):
            return files

        filtered: list[dict[str, str]] = []
        for item in files:
            baseline_item = baseline_files.get(item["path"])
            if not isinstance(baseline_item, dict):
                filtered.append(item)
                continue

            current_fingerprint = self._fingerprint_repo_file(repo_root, item["path"])
            if (
                baseline_item.get("status") != item["status"]
                or baseline_item.get("path") != item["path"]
                or baseline_item.get("originalPath") != item["originalPath"]
                or baseline_item.get("fingerprint") != current_fingerprint
            ):
                filtered.append(item)
        return filtered

    def _tracked_git_paths(self, files: list[dict[str, str]]) -> list[str]:
        pathspecs: list[str] = []
        seen: set[str] = set()
        for item in files:
            if item["status"] == "??":
                continue
            for path_text in (item["originalPath"], item["path"]):
                normalized = str(path_text or "").strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                pathspecs.append(normalized)
        return pathspecs

    def _git_diff_output(self, repo_root: Path, args: list[str], pathspecs: list[str]) -> str:
        if not pathspecs:
            return ""
        return self._git_output(repo_root, [*args, "--", *pathspecs])

    def _fingerprint_repo_file(self, repo_root: Path, path_text: str) -> str:
        candidate = (repo_root / path_text).resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError:
            return "outside-repo"

        if not candidate.exists():
            return "missing"
        if candidate.is_dir():
            try:
                stat = candidate.stat()
                return f"dir:{stat.st_mtime_ns}"
            except OSError:
                return "dir:unreadable"

        digest = hashlib.sha1()
        try:
            with candidate.open("rb") as handle:
                while chunk := handle.read(64 * 1024):
                    digest.update(chunk)
        except OSError:
            return "file:unreadable"

        try:
            size = candidate.stat().st_size
        except OSError:
            size = 0
        return f"file:{size}:{digest.hexdigest()}"

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

    def _prepare_codex_context(self, execution_cwd: Path, skill_instructions: str | None):
        if not skill_instructions:
            return
        agents_path = execution_cwd / "AGENTS.md"
        project_agents = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
        combined = project_agents.rstrip()
        if combined:
            combined += "\n\n"
        combined += f"## Invoked Skill\n{skill_instructions.strip()}\n"
        _write_text(agents_path, combined)

    def _claude_supports_flag(self, flag: str) -> bool:
        if self._claude_help_text is None:
            try:
                executable = self._resolve_cli(settings.CLAUDE_CODE_CLI_PATH, "claude")
                result = subprocess.run(
                    [executable, "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self._claude_help_text = f"{result.stdout}\n{result.stderr}"
            except Exception:
                self._claude_help_text = ""
        return flag in (self._claude_help_text or "")

    def _create_git_worktree(self, repo_path: Path, worktree_path: Path, branch_name: str) -> bool:
        repo_root = self._get_git_root(repo_path)
        if not repo_root:
            return False
        if worktree_path.exists():
            return True
        try:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"],
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

    def adopt_run(self, run_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if not run:
                return {"success": False, "error": "Run 不存在"}
            if run.status != "passed":
                return {"success": False, "error": "只有 passed 的 Run 才能采纳"}

            worktree_path = Path(str((run.metadata_ or {}).get("worktree") or "")).resolve() if (run.metadata_ or {}).get("worktree") else None
            if worktree_path:
                return self._adopt_via_worktree_merge(run, worktree_path, db)

            patch_content = self._artifact_content(db, run_id, "patch")
            if patch_content:
                return self._adopt_via_patch(run, patch_content, db)

            return {"success": False, "error": "没有可采纳的变更"}
        finally:
            db.close()

    def _adopt_via_worktree_merge(self, run: Run, worktree: Path, db) -> dict[str, Any]:
        repo_path = self._resolve_repo_path(run.thread.project)
        if not repo_path:
            return {"success": False, "error": "项目没有可用仓库"}

        branch = str((run.metadata_ or {}).get("worktreeBranch") or "").strip()
        if not branch:
            return {"success": False, "error": "worktree 分支信息缺失"}

        if not self._git_tracked_clean(repo_path):
            return {"success": False, "error": "目标仓库存在未提交的跟踪文件变更，无法自动 merge"}

        worktree_status = self._git_output(worktree, ["status", "--short", "--untracked-files=all"])
        if worktree_status.strip():
            try:
                subprocess.run(
                    ["git", "-C", str(worktree), "add", "-A"],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(worktree),
                        "-c",
                        "user.name=KAM",
                        "-c",
                        "user.email=kam@example.com",
                        "commit",
                        "-m",
                        f"KAM adopt run {run.id}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except subprocess.CalledProcessError as exc:
                return {"success": False, "error": (exc.stderr or exc.stdout or "worktree 提交失败").strip()}

        try:
            subprocess.run(
                ["git", "-C", str(repo_path), "merge", "--no-ff", "--no-edit", branch],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.CalledProcessError as exc:
            return {"success": False, "error": (exc.stderr or exc.stdout or "merge 失败").strip()}

        adopted_at = datetime.utcnow()
        run.adopted_at = adopted_at
        run.metadata_ = {
            **(run.metadata_ or {}),
            "adopted": True,
            "adoptedAt": adopted_at.isoformat(),
            "adoptedVia": "worktree-merge",
        }
        db.commit()
        self._cleanup_run_worktree(run)
        self._record_adoption_memory(db, run)
        event_bus.publish(
            f"thread:{run.thread_id}",
            {
                "type": "thread-updated",
                "runId": str(run.id),
                "threadId": str(run.thread_id),
                "status": run.status,
            },
        )
        return {"success": True}

    def _adopt_via_patch(self, run: Run, patch_content: str, db) -> dict[str, Any]:
        repo_path = self._resolve_repo_path(run.thread.project)
        if not repo_path:
            return {"success": False, "error": "项目没有可用仓库"}
        if not self._git_tracked_clean(repo_path):
            return {"success": False, "error": "目标仓库存在未提交的跟踪文件变更，无法自动应用 patch"}

        patch_path = Path(run.work_dir or settings.AGENT_WORKROOT) / "adopt.patch"
        _write_text(patch_path, patch_content)
        try:
            subprocess.run(
                ["git", "-C", str(repo_path), "apply", "--index", str(patch_path)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.CalledProcessError as exc:
            return {"success": False, "error": (exc.stderr or exc.stdout or "patch 应用失败").strip()}

        adopted_at = datetime.utcnow()
        run.adopted_at = adopted_at
        run.metadata_ = {
            **(run.metadata_ or {}),
            "adopted": True,
            "adoptedAt": adopted_at.isoformat(),
            "adoptedVia": "patch",
        }
        db.commit()
        self._record_adoption_memory(db, run)
        event_bus.publish(
            f"thread:{run.thread_id}",
            {
                "type": "thread-updated",
                "runId": str(run.id),
                "threadId": str(run.thread_id),
                "status": run.status,
            },
        )
        return {"success": True}

    def _cleanup_run_worktree(self, run: Run | None):
        if not run:
            return
        metadata = run.metadata_ or {}
        worktree_value = str(metadata.get("worktree") or "").strip()
        branch = str(metadata.get("worktreeBranch") or "").strip()
        if not worktree_value:
            return

        repo_path = self._resolve_repo_path(run.thread.project)
        repo_root = self._get_git_root(repo_path) if repo_path else None
        if repo_root:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "remove", "--force", worktree_value],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if branch:
                subprocess.run(
                    ["git", "-C", str(repo_root), "branch", "-D", branch],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

    def _git_tracked_clean(self, repo_path: Path) -> bool:
        unstaged = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--quiet", "HEAD", "--"],
            check=False,
        )
        staged = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--cached", "--quiet", "HEAD", "--"],
            check=False,
        )
        return unstaged.returncode == 0 and staged.returncode == 0

    def _record_adoption_memory(self, db, run: Run) -> None:
        compare_group_id = (run.metadata_ or {}).get("compareGroupId")
        compare_prompt = str((run.metadata_ or {}).get("comparePrompt") or "").strip()
        compare_label = str((run.metadata_ or {}).get("compareLabel") or run.agent).strip()
        if not compare_group_id or not compare_prompt or not run.thread.project_id:
            return

        summary = " ".join(self._artifact_content(db, run.id, "summary").strip().split())
        reasoning = f"用户在 Compare 中采纳了方案：{compare_label}。"
        if summary:
            reasoning = f"{reasoning} 结果摘要：{summary[:240]}"

        MemoryService(db).ensure_decision(
            {
                "projectId": str(run.thread.project_id),
                "question": compare_prompt,
                "decision": compare_label,
                "reasoning": reasoning,
                "sourceThreadId": str(run.thread_id),
            }
        )

    def _is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancel_flags

    def _record_thread_event(
        self,
        db,
        run: Run | None,
        content: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ):
        if not run:
            return
        thread = db.query(Thread).filter(Thread.id == run.thread_id).first()
        if thread:
            thread.updated_at = datetime.utcnow()
        event = Message(
            thread_id=run.thread_id,
            role="system",
            content=content,
            metadata_={
                "eventType": event_type,
                "runId": str(run.id),
                "agent": run.agent,
                "status": run.status,
                "round": run.round,
                **(metadata or {}),
            },
        )
        db.add(event)

    def _mark_cancelled(self, db, run_id: str, message: str):
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return
        self._mark_terminal_run(
            db,
            run,
            status="cancelled",
            event_type="run-cancelled",
            content=f"{run.agent} 已取消",
            error=message,
        )


    def _capture_project_learning(self, db, run: Run | None, summary_text: str):
        if not run:
            return
        project_id = None
        if getattr(run, 'thread', None) and getattr(run.thread, 'project_id', None):
            project_id = str(run.thread.project_id)
        if not project_id:
            thread = db.query(Thread).filter(Thread.id == run.thread_id).first()
            if thread and thread.project_id:
                project_id = str(thread.project_id)
        if not project_id:
            return

        content = " ".join((summary_text or "").strip().split())
        if not content:
            return

        MemoryService(db).ensure_learning(
            {
                'projectId': project_id,
                'content': content,
                'sourceThreadId': str(run.thread_id),
            }
        )

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
