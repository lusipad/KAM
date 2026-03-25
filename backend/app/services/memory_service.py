"""
KAM v2 记忆服务
"""
from __future__ import annotations

import math
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.memory import DecisionLog, ProjectLearning, UserPreference


class MemoryService:
    def __init__(self, db: Session):
        self.db = db

    def list_preferences(self, category: str | None = None) -> list[UserPreference]:
        query = self.db.query(UserPreference)
        if category:
            query = query.filter(UserPreference.category == category)
        return query.order_by(UserPreference.created_at.desc()).all()

    def create_preference(self, data: dict[str, Any]) -> UserPreference:
        existing = (
            self.db.query(UserPreference)
            .filter(UserPreference.category == data["category"], UserPreference.key == data["key"])
            .first()
        )
        if existing:
            existing.value = data["value"]
            existing.source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
            self.db.commit()
            self.db.refresh(existing)
            return existing

        preference = UserPreference(
            category=data["category"],
            key=data["key"],
            value=data["value"],
            source_thread_id=data.get("sourceThreadId") or data.get("source_thread_id"),
        )
        self.db.add(preference)
        self.db.commit()
        self.db.refresh(preference)
        return preference

    def update_preference(self, preference_id: str, data: dict[str, Any]) -> UserPreference | None:
        preference = self.db.query(UserPreference).filter(UserPreference.id == preference_id).first()
        if not preference:
            return None
        if "value" in data:
            preference.value = data["value"]
        if "sourceThreadId" in data or "source_thread_id" in data:
            preference.source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
        self.db.commit()
        self.db.refresh(preference)
        return preference

    def list_decisions(self, project_id: str | None = None) -> list[DecisionLog]:
        query = self.db.query(DecisionLog)
        if project_id:
            query = query.filter(DecisionLog.project_id == project_id)
        return query.order_by(DecisionLog.created_at.desc()).all()

    def create_decision(self, data: dict[str, Any]) -> DecisionLog:
        decision = DecisionLog(
            project_id=data.get("projectId") or data.get("project_id"),
            question=data["question"],
            decision=data["decision"],
            reasoning=data.get("reasoning", ""),
            source_thread_id=data.get("sourceThreadId") or data.get("source_thread_id"),
        )
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def ensure_decision(self, data: dict[str, Any]) -> DecisionLog:
        project_id = data.get("projectId") or data.get("project_id")
        source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
        question = str(data.get("question") or "").strip()
        decision_value = str(data.get("decision") or "").strip()
        reasoning = str(data.get("reasoning") or "").strip()

        existing = (
            self.db.query(DecisionLog)
            .filter(
                DecisionLog.project_id == project_id,
                DecisionLog.question == question,
                DecisionLog.source_thread_id == source_thread_id,
            )
            .order_by(DecisionLog.created_at.desc())
            .first()
        )
        if existing:
            existing.decision = decision_value or existing.decision
            if reasoning:
                existing.reasoning = reasoning
            self.db.commit()
            self.db.refresh(existing)
            return existing
        return self.create_decision(data)

    def update_decision(self, decision_id: str, data: dict[str, Any]) -> DecisionLog | None:
        decision = self.db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
        if not decision:
            return None
        if "question" in data:
            decision.question = data["question"]
        if "decision" in data:
            decision.decision = data["decision"]
        if "reasoning" in data:
            decision.reasoning = data.get("reasoning", "")
        if "sourceThreadId" in data or "source_thread_id" in data:
            decision.source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def list_learnings(self, project_id: str | None = None, query: str | None = None) -> list[ProjectLearning]:
        statement = self.db.query(ProjectLearning)
        if project_id:
            statement = statement.filter(ProjectLearning.project_id == project_id)
        if query:
            statement = statement.filter(ProjectLearning.content.contains(query))
        return statement.order_by(ProjectLearning.created_at.desc()).all()

    def create_learning(self, data: dict[str, Any]) -> ProjectLearning:
        content = str(data["content"]).strip()
        learning = ProjectLearning(
            project_id=data.get("projectId") or data.get("project_id"),
            content=content,
            embedding=self._resolve_learning_embedding(content=content, embedding=data.get("embedding")),
            source_thread_id=data.get("sourceThreadId") or data.get("source_thread_id"),
        )
        self.db.add(learning)
        self.db.commit()
        self.db.refresh(learning)
        return learning

    def ensure_learning(self, data: dict[str, Any]) -> ProjectLearning | None:
        project_id = data.get("projectId") or data.get("project_id")
        if not project_id:
            return None

        content = " ".join(str(data.get("content") or "").strip().split())
        if len(content) < 18:
            return None
        if content.lower() in {"ok", "done", "passed", "success", "smoke run ok"}:
            return None

        source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
        existing = (
            self.db.query(ProjectLearning)
            .filter(ProjectLearning.project_id == project_id, ProjectLearning.content == content)
            .order_by(ProjectLearning.created_at.desc())
            .first()
        )
        if existing:
            if source_thread_id and not existing.source_thread_id:
                existing.source_thread_id = source_thread_id
                self.db.commit()
                self.db.refresh(existing)
            return existing

        return self.create_learning(
            {
                **data,
                "projectId": project_id,
                "content": content,
                "sourceThreadId": source_thread_id,
            }
        )

    def update_learning(self, learning_id: str, data: dict[str, Any]) -> ProjectLearning | None:
        learning = self.db.query(ProjectLearning).filter(ProjectLearning.id == learning_id).first()
        if not learning:
            return None
        if "content" in data:
            learning.content = str(data["content"]).strip()
        if "content" in data or "embedding" in data:
            learning.embedding = self._resolve_learning_embedding(
                content=learning.content,
                embedding=data.get("embedding") if "embedding" in data else None,
            )
        if "sourceThreadId" in data or "source_thread_id" in data:
            learning.source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
        self.db.commit()
        self.db.refresh(learning)
        return learning

    def search(self, query: str, project_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
        preferences_query = self.db.query(UserPreference)
        decisions_query = self.db.query(DecisionLog)
        learnings_query = self.db.query(ProjectLearning)

        if project_id:
            decisions_query = decisions_query.filter(DecisionLog.project_id == project_id)
            learnings_query = learnings_query.filter(ProjectLearning.project_id == project_id)

        if query:
            preferences_query = preferences_query.filter(
                (UserPreference.key.contains(query)) | (UserPreference.value.contains(query))
            )
            decisions_query = decisions_query.filter(
                (DecisionLog.question.contains(query))
                | (DecisionLog.decision.contains(query))
                | (DecisionLog.reasoning.contains(query))
            )
            learnings_query = learnings_query.filter(ProjectLearning.content.contains(query))

        lexical_learnings = learnings_query.order_by(ProjectLearning.created_at.desc()).limit(20).all()
        semantic_learnings = self._semantic_search_learnings(query=query, project_id=project_id)
        return {
            "preferences": [item.to_dict() for item in preferences_query.order_by(UserPreference.created_at.desc()).limit(20).all()],
            "decisions": [item.to_dict() for item in decisions_query.order_by(DecisionLog.created_at.desc()).limit(20).all()],
            "learnings": self._merge_learning_results(semantic_learnings, lexical_learnings),
        }

    def _resolve_learning_embedding(self, *, content: str, embedding: Any) -> list[float] | None:
        if isinstance(embedding, list) and embedding:
            values = [float(item) for item in embedding]
            return values or None
        if not content or not settings.OPENAI_API_KEY.strip():
            return None
        return self._embed_text(content)

    def _embed_text(self, text: str) -> list[float] | None:
        try:
            response = httpx.post(
                f"{settings.OPENAI_BASE_URL.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.OPENAI_EMBEDDING_MODEL,
                    "input": text,
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or []
            if not data:
                return None
            embedding = data[0].get("embedding") or []
            if not isinstance(embedding, list):
                return None
            return [float(item) for item in embedding]
        except Exception:
            return None

    def _semantic_search_learnings(self, *, query: str, project_id: str | None) -> list[dict[str, Any]]:
        normalized_query = str(query or "").strip()
        if not normalized_query or not settings.OPENAI_API_KEY.strip():
            return []

        query_embedding = self._embed_text(normalized_query)
        if not query_embedding:
            return []

        statement = self.db.query(ProjectLearning)
        if project_id:
            statement = statement.filter(ProjectLearning.project_id == project_id)

        ranked: list[tuple[float, ProjectLearning]] = []
        for learning in statement.order_by(ProjectLearning.created_at.desc()).limit(200).all():
            embedding = learning.embedding
            if not isinstance(embedding, list) or not embedding:
                continue
            score = self._cosine_similarity(query_embedding, embedding)
            if score <= 0:
                continue
            ranked.append((score, learning))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                **learning.to_dict(),
                "semanticScore": round(score, 6),
            }
            for score, learning in ranked[:20]
        ]

    def _merge_learning_results(
        self,
        semantic_learnings: list[dict[str, Any]],
        lexical_learnings: list[ProjectLearning],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in semantic_learnings:
            item_id = str(item.get("id") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            merged.append(item)

        for learning in lexical_learnings:
            item = learning.to_dict()
            item_id = item["id"]
            if item_id in seen:
                continue
            seen.add(item_id)
            merged.append(item)

        return merged[:20]

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        size = min(len(left), len(right))
        if size == 0:
            return 0.0

        numerator = sum(float(left[index]) * float(right[index]) for index in range(size))
        left_norm = math.sqrt(sum(float(left[index]) ** 2 for index in range(size)))
        right_norm = math.sqrt(sum(float(right[index]) ** 2 for index in range(size)))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
