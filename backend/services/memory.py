from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
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
        cleaned_content = content.strip()
        subject = self._subject_key(cleaned_content)
        existing = await self._find_latest_by_subject(project_id, category, subject)
        if existing and self._normalize_text(existing.content) == self._normalize_text(cleaned_content):
            existing.last_accessed_at = now()
            existing.relevance_score = min(5.0, round(existing.relevance_score + 0.2, 2))
            if rationale and rationale.strip():
                existing.rationale = rationale.strip()
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        memory = Memory(
            project_id=project_id,
            scope=scope,
            category=category,
            content=cleaned_content,
            rationale=rationale.strip() if rationale else None,
            relevance_score=self._base_relevance_for(category, existing),
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
        ranked = sorted(all_memories, key=lambda item: self._score(item, query), reverse=True)
        result = [item for item in ranked if self._score(item, query) > 0][:limit]
        for item in result:
            item.relevance_score = min(5.0, round(item.relevance_score + 0.1, 2))
            item.last_accessed_at = now()
        await self.db.commit()
        return result

    async def build_context_pack(
        self,
        project_id: str | None,
        query: str = "",
        *,
        always_budget_tokens: int | None = None,
        relevant_budget_tokens: int | None = None,
    ) -> dict[str, Any]:
        always_budget = always_budget_tokens or settings.memory_always_inject_tokens
        relevant_budget = relevant_budget_tokens or settings.memory_search_tokens
        always_candidates = await self._select_memories(project_id, {"preference", "decision"}, limit=12)
        always, always_lines, always_used = self._fit_budget(always_candidates, always_budget)

        relevant_candidates = await self.search(project_id=project_id, query=query, limit=12) if query.strip() else []
        relevant_candidates = [item for item in relevant_candidates if item.id not in {memory.id for memory in always}]
        relevant, relevant_lines, relevant_used = self._fit_budget(relevant_candidates, relevant_budget)

        text_lines: list[str] = []
        if always_lines:
            text_lines.append("## Active memory")
            text_lines.extend(always_lines)
        if relevant_lines:
            text_lines.append("## Relevant memory")
            text_lines.extend(relevant_lines)

        return {
            "always": always,
            "relevant": relevant,
            "highlights": [memory.content for memory in always + relevant],
            "text": "\n".join(text_lines),
            "budget": {
                "alwaysTokens": always_budget,
                "relevantTokens": relevant_budget,
                "usedTokens": always_used + relevant_used,
            },
        }

    async def build_context_block(self, project_id: str | None, query: str = "") -> str:
        pack = await self.build_context_pack(project_id, query)
        return pack["text"]

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

    def _fit_budget(self, memories: list[Memory], budget_tokens: int) -> tuple[list[Memory], list[str], int]:
        used_tokens = 0
        selected_memories: list[Memory] = []
        selected_lines: list[str] = []
        for memory in memories:
            line = self._format_memory_line(memory)
            line_tokens = self._estimate_tokens(line)
            if selected_lines and used_tokens + line_tokens > budget_tokens:
                continue
            if not selected_lines and line_tokens > budget_tokens:
                line = self._truncate_text(line, max(80, budget_tokens * 4))
                line_tokens = self._estimate_tokens(line)
            if line_tokens > budget_tokens and selected_lines:
                continue
            selected_memories.append(memory)
            selected_lines.append(line)
            used_tokens += line_tokens
        return selected_memories, selected_lines, used_tokens

    def _score(self, memory: Memory, query: str) -> float:
        query_terms = self._extract_terms(query)
        if not query_terms:
            return memory.relevance_score

        haystack = self._normalize_text(f"{memory.content} {memory.rationale or ''}")
        haystack_terms = self._extract_terms(haystack)
        overlap = len(query_terms & haystack_terms)
        if overlap == 0 and self._normalize_text(query) not in haystack:
            return 0.0

        query_subject = self._subject_key(query)
        subject_bonus = 1.35 if query_subject and query_subject == self._subject_key(memory.content) else 1.0
        exact_bonus = 1.3 if self._normalize_text(query) in haystack else 1.0
        category_bonus = 1.2 if memory.category in {"preference", "decision"} else 1.0
        last_accessed = memory.last_accessed_at
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=UTC)
        freshness = 1.0 if last_accessed >= datetime.now(UTC) - timedelta(days=3) else 0.75
        return overlap * memory.relevance_score * freshness * subject_bonus * exact_bonus * category_bonus

    def _base_relevance_for(self, category: str, existing: Memory | None) -> float:
        base = {
            "decision": 2.4,
            "preference": 2.0,
            "fact": 1.5,
            "learning": 1.3,
        }.get(category, 1.0)
        if existing is None:
            return base
        return min(5.0, max(base, round(existing.relevance_score + 0.1, 2)))

    def _subject_key(self, content: str) -> str:
        normalized = self._normalize_text(content)
        normalized = re.sub(
            r"^(决定|偏好|原则|约定|事实|结论|learned|lesson|fact|decision|preference)\s*[:：]?\s*",
            "",
            normalized,
        )
        for separator in (" 只", " 不", " 默认", " 使用", " 走", " should ", " must ", " use ", " keep "):
            if separator in normalized:
                normalized = normalized.split(separator, 1)[0]
                break
        clause = re.split(r"[,:：，。.;；!?！？\n]", normalized, maxsplit=1)[0].strip()
        return (clause or normalized)[:48]

    def _format_memory_line(self, memory: Memory) -> str:
        rationale = f" ({memory.rationale})" if memory.rationale else ""
        return f"- [{memory.category}] {memory.content}{rationale}"

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    def _extract_terms(self, text: str) -> set[str]:
        lowered = self._normalize_text(text)
        ascii_terms = re.findall(r"[a-z0-9_./-]+", lowered)
        han_chunks = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
        han_text = "".join(re.findall(r"[\u4e00-\u9fff]", text))
        han_ngrams = {
            han_text[index : index + size]
            for size in (2, 3, 4)
            for index in range(0, max(0, len(han_text) - size + 1))
        }
        return {term for term in ascii_terms + han_chunks + list(han_ngrams) if term}

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        ascii_chars = sum(1 for char in text if ord(char) < 128)
        non_ascii_chars = len(text) - ascii_chars
        return max(1, ascii_chars // 4 + non_ascii_chars)

    def _truncate_text(self, text: str, limit: int) -> str:
        compact = text.strip()
        if len(compact) <= limit:
            return compact
        return f"{compact[: max(0, limit - 1)]}…"
