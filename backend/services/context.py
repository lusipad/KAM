from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Project, Thread, WatcherEvent
from services.memory import MemoryService


class ContextAssembler:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(self, *, thread_id: str, project_id: str | None, query: str) -> dict[str, Any]:
        thread = await self._get_thread(thread_id)
        project = await self._get_project(project_id)
        memory_block = await MemoryService(self.db).build_context_block(project_id, query)
        recent_context = await self._recent_context(thread)
        project_block = self._project_block(project)
        return {
            "project": project,
            "thread": thread,
            "project_block": project_block,
            "memory_block": memory_block,
            "recent_context": recent_context,
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

    def _project_block(self, project: Project | None) -> str:
        if project is None:
            return "## Current project\nNo project selected."
        lines = ["## Current project", project.title]
        if project.repo_path:
            lines.append(f"Repo: {project.repo_path}")
        return "\n".join(lines)

    async def _recent_context(self, thread: Thread | None) -> str:
        lines = ["## Recent context"]
        if thread is None:
            lines.append("No recent conversation.")
            return "\n".join(lines)
        for message in thread.messages[-4:]:
            content = message.content.strip().replace("\n", " ")
            preview = content[:160] + ("..." if len(content) > 160 else "")
            lines.append(f"- {message.role}: {preview}")
        for run in thread.runs[-3:]:
            lines.append(f"- Run [{run.status}] {run.task[:100]}")
        stmt = (
            select(WatcherEvent)
            .where(WatcherEvent.thread_id == thread.id)
            .order_by(desc(WatcherEvent.created_at))
            .limit(2)
        )
        result = await self.db.execute(stmt)
        for event in result.scalars():
            lines.append(f"- Watcher [{event.event_type}] {event.title}")
        return "\n".join(lines)
