"""
自治会话服务
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import ROOT_DIR
from app.models.workspace import AutonomySession, TaskCard, TaskRef
from app.services.autonomy_manager import autonomy_manager


class AutonomyService:
    def __init__(self, db: Session):
        self.db = db

    def list_sessions(self, task_id: str) -> list[AutonomySession]:
        return (
            self.db.query(AutonomySession)
            .filter(AutonomySession.task_id == task_id)
            .order_by(AutonomySession.created_at.desc())
            .all()
        )

    def get_session(self, session_id: str) -> AutonomySession | None:
        return self.db.query(AutonomySession).filter(AutonomySession.id == session_id).first()

    def create_session(self, task_id: str, data: dict[str, Any]) -> AutonomySession | None:
        task = self.db.query(TaskCard).filter(TaskCard.id == task_id).first()
        if not task:
            return None

        repo_path = data.get("repoPath") or data.get("repo_path")
        if repo_path:
            self._ensure_repo_ref(task, str(repo_path))

        check_commands = [
            {
                "label": str(item.get("label") or f"检查 {index + 1}"),
                "command": str(item.get("command") or "").strip(),
            }
            for index, item in enumerate(data.get("checkCommands") or data.get("check_commands") or [])
            if str(item.get("command") or "").strip()
        ]

        session = AutonomySession(
            task_id=task.id,
            title=data.get("title") or f"{task.title} / 自治会话",
            objective=data.get("objective", ""),
            status="draft",
            repo_path=str(repo_path) if repo_path else None,
            primary_agent_name=data.get("primaryAgentName") or data.get("primary_agent_name") or "Codex",
            primary_agent_type=data.get("primaryAgentType") or data.get("primary_agent_type") or "codex",
            primary_agent_command=data.get("primaryAgentCommand") or data.get("primary_agent_command"),
            max_iterations=max(1, min(int(data.get("maxIterations") or data.get("max_iterations") or 3), 12)),
            current_iteration=0,
            interruption_count=0,
            success_criteria=data.get("successCriteria") or data.get("success_criteria") or "",
            check_commands=check_commands,
            metadata_=data.get("metadata") or {},
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def create_dogfood_session(self, task_id: str) -> AutonomySession | None:
        repo_path = str(ROOT_DIR.resolve())
        payload = {
            "title": "KAM Dogfood",
            "objective": "让 AI 在当前仓库里持续推进任务，并用真实工程检查来验证输出质量。",
            "repoPath": repo_path,
            "primaryAgentName": "Codex",
            "primaryAgentType": "codex",
            "maxIterations": 4,
            "successCriteria": (
                "本轮修改完成后，前端 lint/build/e2e 与后端单测全部通过；"
                "如检查失败，必须继续下一轮修复，直到通过或达到上限。"
            ),
            "checkCommands": self._build_dogfood_checks(repo_path),
            "metadata": {
                "template": "kam-dogfood",
            },
        }
        return self.create_session(task_id, payload)

    def start_session(self, session_id: str) -> AutonomySession | None:
        session = self.get_session(session_id)
        if not session:
            return None

        if session.status == "running":
            return session
        if session.status in {"completed"}:
            return session

        launched = autonomy_manager.launch_session(str(session.id))
        if not launched:
            return session

        self.db.expire(session)
        self.db.refresh(session)
        return session

    def interrupt_session(self, session_id: str) -> AutonomySession | None:
        session = self.get_session(session_id)
        if not session:
            return None

        if session.status != "running":
            return session

        autonomy_manager.interrupt_session(str(session.id))
        self.db.expire(session)
        self.db.refresh(session)
        return session

    def get_metrics(self, task_id: str | None = None) -> dict[str, Any]:
        query = self.db.query(AutonomySession)
        if task_id:
            query = query.filter(AutonomySession.task_id == task_id)

        sessions = query.all()
        terminal_sessions = [session for session in sessions if session.status in {"completed", "failed", "interrupted"}]
        completed_sessions = [session for session in terminal_sessions if session.status == "completed"]
        interrupted_sessions = [session for session in terminal_sessions if session.status == "interrupted"]
        autonomous_sessions = [
            session
            for session in completed_sessions
            if (session.interruption_count or 0) == 0
        ]

        denominator = len(terminal_sessions) or 1
        completed_cycle_counts = [session.current_iteration or 0 for session in completed_sessions]
        return {
            "totalSessions": len(sessions),
            "activeSessions": sum(1 for session in sessions if session.status == "running"),
            "terminalSessions": len(terminal_sessions),
            "completedSessions": len(completed_sessions),
            "failedSessions": sum(1 for session in terminal_sessions if session.status == "failed"),
            "interruptedSessions": len(interrupted_sessions),
            "autonomyCompletionRate": len(autonomous_sessions) / denominator if terminal_sessions else 0,
            "interruptionRate": len(interrupted_sessions) / denominator if terminal_sessions else 0,
            "successRate": len(completed_sessions) / denominator if terminal_sessions else 0,
            "averageCompletedIterations": (
                sum(completed_cycle_counts) / len(completed_cycle_counts) if completed_cycle_counts else 0
            ),
        }

    def _ensure_repo_ref(self, task: TaskCard, repo_path: str) -> None:
        normalized_repo_path = str(Path(repo_path).resolve())
        for ref in task.refs or []:
            if ref.ref_type == "repo-path" and str(Path(ref.value).resolve()) == normalized_repo_path:
                return

        self.db.add(
            TaskRef(
                task_id=task.id,
                ref_type="repo-path",
                label="dogfood repo",
                value=normalized_repo_path,
                metadata_={"source": "autonomy"},
            )
        )
        self.db.flush()

    def _build_dogfood_checks(self, repo_path: str) -> list[dict[str, str]]:
        if os.name == "nt":
            return [
                {
                    "label": "App lint",
                    "command": "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'app'); npm run lint",
                },
                {
                    "label": "App build",
                    "command": "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'app'); npm run build",
                },
                {
                    "label": "App e2e",
                    "command": "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'app'); npm run test:e2e",
                },
                {
                    "label": "Backend unit",
                    "command": (
                        "$python = Join-Path '{execution_cwd}' '.venv\\Scripts\\python.exe'; "
                        "if (!(Test-Path $python)) { $python = Join-Path '{repo_path}' '.venv\\Scripts\\python.exe' }; "
                        "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'backend'); "
                        "if (Test-Path $python) { & $python -m unittest discover -s tests -v } else { py -m unittest discover -s tests -v }"
                    ),
                },
            ]

        return [
            {
                "label": "App lint",
                "command": "cd '{execution_cwd}/app' && npm run lint",
            },
            {
                "label": "App build",
                "command": "cd '{execution_cwd}/app' && npm run build",
            },
            {
                "label": "App e2e",
                "command": "cd '{execution_cwd}/app' && npm run test:e2e",
            },
            {
                "label": "Backend unit",
                "command": (
                    "PYTHON_BIN='{execution_cwd}/.venv/bin/python'; "
                    "if [ ! -x \"$PYTHON_BIN\" ]; then PYTHON_BIN='{repo_path}/.venv/bin/python'; fi; "
                    "cd '{execution_cwd}/backend' && "
                    "if [ -x \"$PYTHON_BIN\" ]; then \"$PYTHON_BIN\" -m unittest discover -s tests -v; "
                    "else python -m unittest discover -s tests -v; fi"
                ),
            },
        ]
