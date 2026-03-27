from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from models import Project, Thread, WatcherEvent
from services.memory import MemoryService


class ContextAssembler:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(self, *, thread_id: str, project_id: str | None, query: str) -> dict[str, Any]:
        thread = await self._get_thread(thread_id)
        project = await self._get_project(project_id or getattr(thread, "project_id", None))

        memory_service = MemoryService(self.db)
        memory_pack = await memory_service.build_context_pack(
            project.id if project else None,
            query,
            always_budget_tokens=settings.memory_always_inject_tokens,
            relevant_budget_tokens=settings.memory_search_tokens,
        )

        recent_budget = max(320, settings.context_budget_tokens - memory_pack["budget"]["usedTokens"] - 320)
        recent_pack = await self._recent_context(thread, budget_tokens=recent_budget)
        project_block = self._project_block(project, thread)
        budget = {
            "totalTokens": settings.context_budget_tokens,
            "projectTokens": self._estimate_tokens(project_block),
            "memoryTokens": memory_pack["budget"]["usedTokens"],
            "recentTokens": recent_pack["usedTokens"],
        }
        budget["usedTokens"] = budget["projectTokens"] + budget["memoryTokens"] + budget["recentTokens"]

        prompt_context = "\n\n".join(
            block
            for block in (
                project_block,
                memory_pack["text"],
                recent_pack["text"],
            )
            if block
        )

        return {
            "project": project,
            "thread": thread,
            "project_block": project_block,
            "memory_block": memory_pack["text"],
            "memory_pack": memory_pack,
            "recent_context": recent_pack["text"],
            "recent_activity": recent_pack["items"],
            "prompt_context": prompt_context,
            "budget": budget,
            "has_memory": bool(memory_pack["highlights"]),
            "has_recent_activity": bool(recent_pack["items"]),
        }

    async def _get_thread(self, thread_id: str) -> Thread | None:
        stmt = (
            select(Thread)
            .where(Thread.id == thread_id)
            .options(selectinload(Thread.messages), selectinload(Thread.runs))
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _get_project(self, project_id: str | None) -> Project | None:
        if project_id is None:
            return None
        return await self.db.get(Project, project_id)

    def _project_block(self, project: Project | None, thread: Thread | None) -> str:
        if project is None:
            return "## Current project\nNo project selected."
        lines = ["## Current project", f"项目：{project.title}"]
        if project.repo_path:
            lines.append(f"仓库：{project.repo_path}")
        if thread is not None and thread.title:
            lines.append(f"当前线程：{thread.title}")
        return "\n".join(lines)

    async def _recent_context(self, thread: Thread | None, *, budget_tokens: int) -> dict[str, Any]:
        lines = ["## Recent context"]
        if thread is None:
            lines.append("No recent conversation.")
            return {"text": "\n".join(lines), "items": [], "usedTokens": self._estimate_tokens("\n".join(lines))}

        activity: list[dict[str, Any]] = []
        for message in reversed(thread.messages):
            preview = self._message_preview(message.content)
            if not preview:
                continue
            kind = (message.metadata_ or {}).get("kind")
            if message.role == "system" and kind == "watcher-config":
                watcher_name = ((message.metadata_ or {}).get("watcher") or {}).get("name") or "新监控"
                preview = f"已配置监控 {watcher_name}"
            activity.append(
                {
                    "createdAt": message.created_at,
                    "line": f"- {message.role}: {preview}",
                    "kind": "message",
                }
            )
        for run in reversed(thread.runs):
            summary = self._message_preview(run.result_summary or run.task, limit=140)
            activity.append(
                {
                    "createdAt": run.created_at,
                    "line": f"- run[{run.status}]: {summary}",
                    "kind": "run",
                }
            )

        stmt = (
            select(WatcherEvent)
            .where(WatcherEvent.thread_id == thread.id)
            .order_by(desc(WatcherEvent.created_at))
            .limit(4)
        )
        result = await self.db.execute(stmt)
        for event in result.scalars():
            activity.append(
                {
                    "createdAt": event.created_at,
                    "line": f"- watcher[{event.event_type}]: {self._message_preview(event.title, limit=140)}",
                    "kind": "watcher_event",
                }
            )

        activity.sort(key=lambda item: self._timestamp(item["createdAt"]), reverse=True)

        used_tokens = self._estimate_tokens("## Recent context")
        selected: list[dict[str, Any]] = []
        for item in activity:
            line_tokens = self._estimate_tokens(item["line"])
            if selected and used_tokens + line_tokens > budget_tokens:
                continue
            if not selected and line_tokens > budget_tokens:
                continue
            selected.append(item)
            used_tokens += line_tokens
            if len(selected) >= 8:
                break

        if not selected:
            lines.append("No recent conversation.")
            text = "\n".join(lines)
            return {"text": text, "items": [], "usedTokens": self._estimate_tokens(text)}

        selected.sort(key=lambda item: self._timestamp(item["createdAt"]))
        lines.extend(item["line"] for item in selected)
        text = "\n".join(lines)
        return {"text": text, "items": selected, "usedTokens": self._estimate_tokens(text)}

    def _message_preview(self, content: str | None, *, limit: int = 160) -> str:
        if not content:
            return ""
        compact = " ".join(content.strip().split())
        if len(compact) <= limit:
            return compact
        return f"{compact[: max(0, limit - 1)]}…"

    def _timestamp(self, value: datetime) -> float:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).timestamp()
        return value.timestamp()

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        ascii_chars = sum(1 for char in text if ord(char) < 128)
        non_ascii_chars = len(text) - ascii_chars
        return max(1, ascii_chars // 4 + non_ascii_chars)
