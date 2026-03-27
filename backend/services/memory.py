from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session
from models import Memory, now


class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, project_id: str | None = None) -> list[Memory]:
        stmt = select(Memory).where(Memory.superseded_by.is_(None)).order_by(Memory.category, Memory.created_at.desc())
        if project_id:
            stmt = stmt.where(or_(Memory.project_id == project_id, Memory.scope == "global"))
        result = await self.db.execute(stmt)
        return list(result.scalars())

    async def record(
        self,
        *,
        project_id: str | None,
        category: str,
        content: str,
        rationale: str | None = None,
        scope: str = "project",
        source_thread_id: str | None = None,
        source_message_id: str | None = None,
    ) -> Memory:
        subject = self._subject_key(content)
        existing = await self._find_latest_by_subject(project_id, category, subject)
        memory = Memory(
            project_id=project_id,
            scope=scope,
            category=category,
            content=content.strip(),
            rationale=rationale,
            source_thread_id=source_thread_id,
            source_message_id=source_message_id,
        )
        self.db.add(memory)
        await self.db.flush()
        if existing and existing.id != memory.id:
            existing.superseded_by = memory.id
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def update(self, memory_id: str, payload: dict[str, Any]) -> Memory | None:
        memory = await self.db.get(Memory, memory_id)
        if memory is None:
            return None
        for key in ("content", "rationale", "category"):
            if key in payload and payload[key] is not None:
                setattr(memory, key, str(payload[key]).strip())
        memory.last_accessed_at = now()
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def search(self, *, project_id: str | None, query: str, limit: int = 8) -> list[Memory]:
        all_memories = await self.list(project_id)
        tokens = {token for token in query.lower().split() if token}
        ranked = sorted(all_memories, key=lambda item: self._score(item, tokens), reverse=True)
        result = [item for item in ranked if self._score(item, tokens) > 0][:limit]
        for item in result:
            item.relevance_score = min(5.0, item.relevance_score + 0.1)
            item.last_accessed_at = now()
        await self.db.commit()
        return result

    async def build_context_block(self, project_id: str | None, query: str = "") -> str:
        always = await self._select_memories(project_id, {"preference", "decision"}, 6)
        searched = await self.search(project_id=project_id, query=query, limit=6) if query.strip() else []
        lines = []
        if always:
            lines.append("## Your memory")
            lines.extend(self._format_memory_lines(always))
        if searched:
            lines.append("## Relevant memory")
            lines.extend(self._format_memory_lines(searched))
        return "\n".join(lines)

    @classmethod
    async def decay_all(cls) -> None:
        async with async_session() as session:
            cutoff = datetime.now(UTC) - timedelta(days=7)
            result = await session.execute(select(Memory).where(Memory.last_accessed_at < cutoff))
            memories = list(result.scalars())
            for memory in memories:
                last_accessed = memory.last_accessed_at
                if last_accessed.tzinfo is None:
                    last_accessed = last_accessed.replace(tzinfo=UTC)
                if last_accessed < cutoff:
                    memory.relevance_score = max(0.5, round(memory.relevance_score - 0.1, 2))
            await session.commit()

    async def _find_latest_by_subject(self, project_id: str | None, category: str, subject: str) -> Memory | None:
        stmt = (
            select(Memory)
            .where(Memory.category == category, Memory.superseded_by.is_(None))
            .order_by(Memory.created_at.desc())
        )
        if project_id:
            stmt = stmt.where(or_(Memory.project_id == project_id, Memory.scope == "global"))
        result = await self.db.execute(stmt)
        for memory in result.scalars():
            if self._subject_key(memory.content) == subject:
                return memory
        return None

    async def _select_memories(self, project_id: str | None, categories: set[str], limit: int) -> list[Memory]:
        stmt = (
            select(Memory)
            .where(Memory.category.in_(categories), Memory.superseded_by.is_(None))
            .order_by(Memory.relevance_score.desc(), Memory.created_at.desc())
            .limit(limit)
        )
        if project_id:
            stmt = stmt.where(or_(Memory.project_id == project_id, Memory.scope == "global"))
        result = await self.db.execute(stmt)
        return list(result.scalars())

    def _score(self, memory: Memory, tokens: set[str]) -> float:
        if not tokens:
            return memory.relevance_score
        haystack = f"{memory.content} {memory.rationale or ''}".lower()
        overlap = sum(1 for token in tokens if token in haystack)
        if overlap == 0:
            return 0.0
        last_accessed = memory.last_accessed_at
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=UTC)
        freshness = 1.0 if last_accessed >= datetime.now(UTC) - timedelta(days=3) else 0.7
        return overlap * memory.relevance_score * freshness

    def _subject_key(self, content: str) -> str:
        normalized = content.split(":", 1)[0].strip().lower()
        return normalized or content.strip().lower()[:32]

    def _format_memory_lines(self, memories: list[Memory]) -> list[str]:
        lines = []
        for memory in memories:
            rationale = f" ({memory.rationale})" if memory.rationale else ""
            lines.append(f"- [{memory.category}] {memory.content}{rationale}")
        return lines
