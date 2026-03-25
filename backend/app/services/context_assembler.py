"""
KAM v2 上下文组装器（Phase 4 规则版）
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.conversation import Thread
from app.services.memory_service import MemoryService
from app.services.run_service import RunService


class ContextAssembler:
    def __init__(self, db: Session):
        self.db = db
        self.memory_service = MemoryService(db)
        self.run_service = RunService(db)

    def assemble(self, thread_id: str) -> dict[str, Any] | None:
        thread = self.db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            return None

        project = thread.project
        project_id = str(project.id) if project else None
        recent_runs = [run.to_dict(include_artifacts=False) for run in self.run_service.list_runs(thread_id)[:3]]
        preferences = [item.to_dict() for item in self.memory_service.list_preferences()[:20]]
        decisions = [
            item.to_dict()
            for item in self.memory_service.list_decisions(project_id=project_id)[:5]
        ]
        learnings = [
            item.to_dict()
            for item in self.memory_service.list_learnings(project_id=project_id)[:8]
        ]
        recent_messages = [message.to_dict() for message in (thread.messages or [])[-10:]]

        return {
            "summary": self._summarize_thread(thread),
            "project": project.to_dict(include_relations=True, include_threads=False) if project else None,
            "thread": thread.to_dict(include_relations=False),
            "pinnedResources": project.to_dict(include_relations=True).get("pinnedResources", []) if project else [],
            "recentMessages": recent_messages,
            "recentRuns": recent_runs,
            "preferences": preferences,
            "decisions": decisions,
            "learnings": learnings,
        }

    def _summarize_thread(self, thread: Thread) -> str:
        if not thread.messages:
            return "暂无对话历史。"
        parts: list[str] = []
        for message in list(thread.messages)[-6:]:
            role = message.role.upper()
            text = message.content.strip().replace("\n", " ")
            parts.append(f"- {role}: {text[:120]}")
        return "\n".join(parts)
