"""
KAM v2 上下文组装器。
"""
from __future__ import annotations

import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
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
        message_records = [message.to_dict() for message in (thread.messages or [])]
        recent_runs = self._build_recent_runs(thread_id)
        memory_query = self._build_memory_query(thread)
        searched_memories = self.memory_service.search(query=memory_query, project_id=project_id) if memory_query else {}
        preferences = searched_memories.get("preferences") or [item.to_dict() for item in self.memory_service.list_preferences()[:20]]
        decisions = searched_memories.get("decisions") or [
            item.to_dict()
            for item in self.memory_service.list_decisions(project_id=project_id)[:10]
        ]
        learnings = searched_memories.get("learnings") or [
            item.to_dict()
            for item in self.memory_service.list_learnings(project_id=project_id)[:10]
        ]
        pinned_resources = project.to_dict(include_relations=True).get("pinnedResources", []) if project else []

        budget = max(int(settings.CONTEXT_TOKEN_BUDGET or 8000), 2000)
        history_text = self._compress_thread_history(message_records)
        resource_items = self._truncate_items(
            pinned_resources,
            budget=max(400, budget // 8),
            serializer=lambda item: f"[{item.get('type')}] {item.get('title') or item.get('uri')}: {item.get('uri')}",
        )
        preference_items = self._truncate_items(
            preferences,
            budget=max(400, budget // 8),
            serializer=lambda item: f"{item.get('category')} / {item.get('key')}: {item.get('value')}",
        )
        decision_items = self._truncate_items(
            decisions,
            budget=max(400, budget // 8),
            serializer=lambda item: f"{item.get('question')}: {item.get('decision')}",
        )
        learning_items = self._truncate_items(
            learnings,
            budget=max(600, budget // 6),
            serializer=lambda item: str(item.get("content") or ""),
        )
        run_items = self._truncate_items(
            recent_runs,
            budget=max(600, budget // 6),
            serializer=lambda item: json.dumps(item, ensure_ascii=False),
        )

        return {
            "summary": self._summarize_thread(message_records),
            "project": project.to_dict(include_relations=True, include_threads=False) if project else None,
            "thread": thread.to_dict(include_relations=False),
            "pinnedResources": resource_items,
            "recentMessages": message_records[-10:],
            "recentRuns": run_items,
            "preferences": preference_items,
            "decisions": decision_items,
            "learnings": learning_items,
            "historyText": history_text,
        }

    def _build_recent_runs(self, thread_id: str) -> list[dict[str, Any]]:
        runs = self.run_service.list_runs(thread_id)[:5]
        payload: list[dict[str, Any]] = []
        for run in runs:
            artifacts = {artifact.artifact_type: artifact for artifact in (run.artifacts or [])}
            payload.append(
                {
                    "id": str(run.id),
                    "agent": run.agent,
                    "status": run.status,
                    "round": run.round,
                    "durationMs": run.duration_ms,
                    "summary": (artifacts.get("summary").content if artifacts.get("summary") else "")[:800],
                    "changes": (artifacts.get("changes").content if artifacts.get("changes") else "")[:600],
                    "checks": (artifacts.get("check_result").content if artifacts.get("check_result") else "")[:600],
                    "createdAt": run.created_at.isoformat() if run.created_at else None,
                    "completedAt": run.completed_at.isoformat() if run.completed_at else None,
                }
            )
        return payload

    def _summarize_thread(self, messages: list[dict[str, Any]]) -> str:
        if not messages:
            return "暂无对话历史。"
        parts: list[str] = []
        for message in messages[-6:]:
            role = str(message.get("role") or "").upper()
            text = " ".join(str(message.get("content") or "").strip().split())
            if not text:
                continue
            parts.append(f"- {role}: {text[:160]}")
        return "\n".join(parts) if parts else "暂无对话历史。"

    def _compress_thread_history(self, messages: list[dict[str, Any]], target_count: int = 20) -> str:
        if not messages:
            return "暂无对话历史。"
        if len(messages) <= target_count:
            return self._format_messages(messages)

        early = messages[:-10]
        recent = messages[-10:]
        early_summary = self._summarize_messages_window(early)
        return f"[历史摘要]\n{early_summary}\n\n[最近对话]\n{self._format_messages(recent)}"

    def _summarize_messages_window(self, messages: list[dict[str, Any]]) -> str:
        slices: list[str] = []
        for message in messages[-10:]:
            role = str(message.get("role") or "").upper()
            content = " ".join(str(message.get("content") or "").strip().split())
            if not content:
                continue
            slices.append(f"{role}: {content[:120]}")
        return " | ".join(slices)[:1200] or "暂无早期上下文。"

    def _format_messages(self, messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages:
            role = str(message.get("role") or "").upper()
            content = " ".join(str(message.get("content") or "").strip().split())
            if not content:
                continue
            lines.append(f"- {role}: {content[:200]}")
        return "\n".join(lines) if lines else "暂无最近消息。"

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _truncate_items(
        self,
        items: list[dict[str, Any]],
        *,
        budget: int,
        serializer: Callable[[dict[str, Any]], str],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        used = 0
        for item in items:
            tokens = self._estimate_tokens(serializer(item))
            if result and used + tokens > budget:
                break
            result.append(item)
            used += tokens
        return result

    def _build_memory_query(self, thread: Thread) -> str:
        parts: list[str] = []
        if thread.title:
            parts.append(thread.title.strip())

        user_messages = [message for message in list(thread.messages or []) if message.role == "user"]
        for message in user_messages[-3:]:
            text = " ".join(message.content.strip().split())
            if text:
                parts.append(text[:240])

        if not parts:
            parts.append(self._summarize_thread([message.to_dict() for message in (thread.messages or [])]))

        query = " ".join(part for part in parts if part).strip()
        return query[:800]
