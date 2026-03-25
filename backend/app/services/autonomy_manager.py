"""
自治会话执行管理器
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db.base import SessionLocal
from app.models.workspace import AgentRun, AutonomyCycle, AutonomySession
from app.services.workspace_service import WorkspaceService


TERMINAL_RUN_STATUSES = {"completed", "failed", "canceled"}
TERMINAL_SESSION_STATUSES = {"completed", "failed", "interrupted"}


def _tail_text(content: str, max_chars: int = 2_000) -> str:
    if len(content) <= max_chars:
        return content
    return content[-max_chars:]


def _slugify(text: str) -> str:
    value = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    return value or "check"


class AutonomyExecutionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}

    def launch_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._threads:
                return False

            stop_event = threading.Event()
            thread = threading.Thread(target=self._run_session, args=(session_id, stop_event), daemon=True)
            self._stop_events[session_id] = stop_event
            self._threads[session_id] = thread
            thread.start()
            return True

    def interrupt_session(self, session_id: str) -> bool:
        with self._lock:
            stop_event = self._stop_events.get(session_id)
        if not stop_event:
            return False

        stop_event.set()

        db = SessionLocal()
        try:
            session = db.query(AutonomySession).filter(AutonomySession.id == session_id).first()
            if not session:
                return False

            active_run_id = (session.metadata_ or {}).get("activeRunId")
            if active_run_id:
                WorkspaceService(db).cancel_run(str(active_run_id))
        finally:
            db.close()

        return True

    def _run_session(self, session_id: str, stop_event: threading.Event) -> None:
        try:
            self._session_loop(session_id, stop_event)
        finally:
            with self._lock:
                self._stop_events.pop(session_id, None)
                self._threads.pop(session_id, None)

    def _session_loop(self, session_id: str, stop_event: threading.Event) -> None:
        db = SessionLocal()
        try:
            session = db.query(AutonomySession).filter(AutonomySession.id == session_id).first()
            if not session:
                return

            session.status = "running"
            session.updated_at = datetime.utcnow()
            session.metadata_ = {
                **(session.metadata_ or {}),
                "startedAt": datetime.utcnow().isoformat(),
                "activeRunId": None,
            }
            db.commit()

            while session.current_iteration < session.max_iterations:
                if stop_event.is_set():
                    self._mark_interrupted(db, session, None, "自治会话已被用户打断")
                    return

                session = db.query(AutonomySession).filter(AutonomySession.id == session_id).first()
                if not session or session.status in TERMINAL_SESSION_STATUSES:
                    return

                previous_cycle = (
                    db.query(AutonomyCycle)
                    .filter(AutonomyCycle.session_id == session.id)
                    .order_by(AutonomyCycle.iteration.desc())
                    .first()
                )
                next_iteration = session.current_iteration + 1

                cycle = AutonomyCycle(
                    session_id=session.id,
                    iteration=next_iteration,
                    status="running",
                    metadata_={},
                )
                db.add(cycle)
                session.current_iteration = next_iteration
                session.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(cycle)

                prompt_appendix = self._build_prompt_appendix(session, previous_cycle, next_iteration)
                agent_payload = {
                    "name": session.primary_agent_name,
                    "type": session.primary_agent_type,
                    "command": session.primary_agent_command,
                    "promptAppendix": prompt_appendix,
                }
                runs = WorkspaceService(db).create_runs(str(session.task_id), [agent_payload], auto_launch=True)
                if not runs:
                    raise RuntimeError("自治会话无法创建 worker run")

                worker_run = runs[0]
                cycle.worker_run_id = worker_run.id
                session.metadata_ = {
                    **(session.metadata_ or {}),
                    "activeRunId": str(worker_run.id),
                    "lastCycleId": str(cycle.id),
                }
                db.commit()

                self._wait_for_run(str(worker_run.id), stop_event)

                db.expire_all()
                session = db.query(AutonomySession).filter(AutonomySession.id == session_id).first()
                cycle = db.query(AutonomyCycle).filter(AutonomyCycle.id == cycle.id).first()
                worker_run = db.query(AgentRun).filter(AgentRun.id == worker_run.id).first()

                if not session or not cycle or not worker_run:
                    return

                if stop_event.is_set():
                    self._mark_interrupted(db, session, cycle, "自治会话已被用户打断")
                    return

                cycle.status = "checking"
                db.commit()

                check_results = self._execute_checks(session, worker_run, cycle.iteration)
                checks_passed = all(item.get("passed") for item in check_results) if check_results else True
                feedback_summary = self._build_feedback(worker_run, check_results)

                cycle.check_results = check_results
                cycle.feedback_summary = feedback_summary
                cycle.completed_at = datetime.utcnow()
                cycle.metadata_ = {
                    **(cycle.metadata_ or {}),
                    "runStatus": worker_run.status,
                    "checksPassed": checks_passed,
                }

                session.metadata_ = {
                    **(session.metadata_ or {}),
                    "activeRunId": None,
                    "lastFeedback": feedback_summary,
                    "lastRunId": str(worker_run.id),
                }
                session.updated_at = datetime.utcnow()

                if worker_run.status == "completed" and checks_passed:
                    cycle.status = "passed"
                    session.status = "completed"
                    session.completed_at = datetime.utcnow()
                    session.metadata_ = {
                        **(session.metadata_ or {}),
                        "completedCycleId": str(cycle.id),
                        "successfulRunId": str(worker_run.id),
                    }
                    db.commit()
                    return

                cycle.status = "failed"
                if cycle.iteration >= session.max_iterations:
                    session.status = "failed"
                    session.completed_at = datetime.utcnow()
                    db.commit()
                    return

                db.commit()

            session = db.query(AutonomySession).filter(AutonomySession.id == session_id).first()
            if session and session.status == "running":
                session.status = "failed"
                session.completed_at = datetime.utcnow()
                session.metadata_ = {
                    **(session.metadata_ or {}),
                    "activeRunId": None,
                    "failureReason": "达到最大迭代次数仍未通过检查",
                }
                db.commit()
        except Exception as exc:
            session = db.query(AutonomySession).filter(AutonomySession.id == session_id).first()
            if session and session.status not in TERMINAL_SESSION_STATUSES:
                session.status = "failed"
                session.completed_at = datetime.utcnow()
                session.updated_at = datetime.utcnow()
                session.metadata_ = {
                    **(session.metadata_ or {}),
                    "activeRunId": None,
                    "failureReason": str(exc),
                }
                db.commit()
        finally:
            db.close()

    def _wait_for_run(self, run_id: str, stop_event: threading.Event) -> None:
        while True:
            db = SessionLocal()
            try:
                run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
                if not run:
                    return

                if stop_event.is_set() and run.status not in TERMINAL_RUN_STATUSES:
                    WorkspaceService(db).cancel_run(run_id)

                if run.status in TERMINAL_RUN_STATUSES:
                    return
            finally:
                db.close()

            time.sleep(1)

    def _execute_checks(self, session: AutonomySession, run: AgentRun, iteration: int) -> list[dict[str, Any]]:
        execution_cwd = Path((run.metadata_ or {}).get("executionCwd") or run.workdir or session.repo_path or ".").resolve()
        run_dir = Path(run.workdir or execution_cwd).resolve()
        repo_path = Path(session.repo_path).resolve() if session.repo_path else execution_cwd
        checks_dir = run_dir / "autonomy-checks" / f"iteration-{iteration:02d}"
        checks_dir.mkdir(parents=True, exist_ok=True)

        results: list[dict[str, Any]] = []
        for index, check in enumerate(session.check_commands or [], start=1):
            label = str(check.get("label") or f"检查 {index}")
            template = str(check.get("command") or "").strip()
            if not template:
                continue

            resolved_command = self._render_check_command(
                template,
                repo_path=repo_path,
                execution_cwd=execution_cwd,
                run_dir=run_dir,
                task_id=str(session.task_id),
            )
            stdout_path = checks_dir / f"{index:02d}-{_slugify(label)}.stdout.log"
            stderr_path = checks_dir / f"{index:02d}-{_slugify(label)}.stderr.log"

            started_at = time.perf_counter()
            try:
                command, display_command = self._build_shell_command(resolved_command)
                completed = subprocess.run(
                    command,
                    cwd=execution_cwd,
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
            stdout_path.write_text(stdout_text, encoding="utf-8")
            stderr_path.write_text(stderr_text, encoding="utf-8")

            results.append(
                {
                    "label": label,
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

    def _render_check_command(
        self,
        template: str,
        *,
        repo_path: Path,
        execution_cwd: Path,
        run_dir: Path,
        task_id: str,
    ) -> str:
        return (
            template.replace("{repo_path}", str(repo_path))
            .replace("{execution_cwd}", str(execution_cwd))
            .replace("{run_dir}", str(run_dir))
            .replace("{task_id}", task_id)
        )

    def _build_shell_command(self, command_text: str) -> tuple[list[str], str]:
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

    def _build_prompt_appendix(
        self,
        session: AutonomySession,
        previous_cycle: AutonomyCycle | None,
        iteration: int,
    ) -> str:
        lines = [
            f"当前自治迭代: {iteration}/{session.max_iterations}",
            "目标: 尽量在不打断用户的前提下完成任务并通过所有检查。",
        ]
        if session.objective:
            lines.extend(["", "本轮目标:", session.objective])
        if session.success_criteria:
            lines.extend(["", "成功标准:", session.success_criteria])
        if previous_cycle and previous_cycle.feedback_summary:
            lines.extend(
                [
                    "",
                    "上一轮失败反馈:",
                    previous_cycle.feedback_summary,
                    "",
                    "请优先修复上述问题，再继续推进任务。",
                ]
            )
        return "\n".join(lines)

    def _build_feedback(self, run: AgentRun, check_results: list[dict[str, Any]]) -> str:
        lines = [
            f"Run 状态: {run.status}",
        ]
        if run.error_message:
            lines.append(f"Run 错误: {run.error_message}")

        summary_artifact = next((artifact for artifact in run.artifacts if artifact.artifact_type == "summary"), None)
        if summary_artifact and summary_artifact.content.strip():
            lines.extend(["", "Run Summary:", _tail_text(summary_artifact.content.strip(), max_chars=4_000)])

        if check_results:
            lines.extend(["", "检查结果:"])
            for check in check_results:
                status = "PASS" if check.get("passed") else "FAIL"
                line = f"- [{status}] {check.get('label')} (exit {check.get('exitCode')})"
                lines.append(line)
                if not check.get("passed"):
                    preview = check.get("stderrPreview") or check.get("stdoutPreview") or ""
                    if preview:
                        lines.append(_tail_text(preview, max_chars=1_000))

        return "\n".join(lines)

    def _mark_interrupted(
        self,
        db,
        session: AutonomySession,
        cycle: AutonomyCycle | None,
        reason: str,
    ) -> None:
        if cycle:
            cycle.status = "interrupted"
            cycle.feedback_summary = reason
            cycle.completed_at = datetime.utcnow()

        session.status = "interrupted"
        session.interruption_count = (session.interruption_count or 0) + 1
        session.completed_at = datetime.utcnow()
        session.updated_at = datetime.utcnow()
        session.metadata_ = {
            **(session.metadata_ or {}),
            "activeRunId": None,
            "interruptedAt": datetime.utcnow().isoformat(),
            "interruptReason": reason,
        }
        db.commit()


autonomy_manager = AutonomyExecutionManager()
