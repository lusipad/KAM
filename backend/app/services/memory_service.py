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
        category = str(data["category"]).strip()
        key = str(data["key"]).strip()
        value = str(data["value"]).strip()
        embedding_text = self._preference_embedding_text(category=category, key=key, value=value)

        existing = (
            self.db.query(UserPreference)
            .filter(UserPreference.category == category, UserPreference.key == key)
            .first()
        )
        if existing:
            existing.category = category
            existing.key = key
            existing.value = value
            existing.embedding = self._resolve_embedding(content=embedding_text, embedding=data.get("embedding"))
            existing.source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
            self.db.commit()
            self.db.refresh(existing)
            return existing

        preference = UserPreference(
            category=category,
            key=key,
            value=value,
            embedding=self._resolve_embedding(content=embedding_text, embedding=data.get("embedding")),
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

        should_refresh_embedding = False
        if "value" in data:
            preference.value = str(data["value"]).strip()
            should_refresh_embedding = True
        if "embedding" in data:
            should_refresh_embedding = True
        if "sourceThreadId" in data or "source_thread_id" in data:
            preference.source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
        if should_refresh_embedding:
            preference.embedding = self._resolve_embedding(
                content=self._preference_embedding_text(
                    category=preference.category,
                    key=preference.key,
                    value=preference.value,
                ),
                embedding=data.get("embedding"),
            )
        self.db.commit()
        self.db.refresh(preference)
        return preference

    def list_decisions(self, project_id: str | None = None) -> list[DecisionLog]:
        query = self.db.query(DecisionLog)
        if project_id:
            query = query.filter(DecisionLog.project_id == project_id)
        return query.order_by(DecisionLog.created_at.desc()).all()

    def create_decision(self, data: dict[str, Any]) -> DecisionLog:
        question = str(data["question"]).strip()
        decision_value = str(data["decision"]).strip()
        reasoning = str(data.get("reasoning") or "").strip()
        decision = DecisionLog(
            project_id=data.get("projectId") or data.get("project_id"),
            question=question,
            decision=decision_value,
            reasoning=reasoning,
            embedding=self._resolve_embedding(
                content=self._decision_embedding_text(
                    question=question,
                    decision=decision_value,
                    reasoning=reasoning,
                ),
                embedding=data.get("embedding"),
            ),
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
            existing.embedding = self._resolve_embedding(
                content=self._decision_embedding_text(
                    question=existing.question,
                    decision=existing.decision,
                    reasoning=existing.reasoning,
                ),
                embedding=data.get("embedding"),
            )
            self.db.commit()
            self.db.refresh(existing)
            return existing
        return self.create_decision(data)

    def update_decision(self, decision_id: str, data: dict[str, Any]) -> DecisionLog | None:
        decision = self.db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
        if not decision:
            return None

        should_refresh_embedding = False
        if "question" in data:
            decision.question = str(data["question"]).strip()
            should_refresh_embedding = True
        if "decision" in data:
            decision.decision = str(data["decision"]).strip()
            should_refresh_embedding = True
        if "reasoning" in data:
            decision.reasoning = str(data.get("reasoning") or "").strip()
            should_refresh_embedding = True
        if "embedding" in data:
            should_refresh_embedding = True
        if "sourceThreadId" in data or "source_thread_id" in data:
            decision.source_thread_id = data.get("sourceThreadId") or data.get("source_thread_id")
        if should_refresh_embedding:
            decision.embedding = self._resolve_embedding(
                content=self._decision_embedding_text(
                    question=decision.question,
                    decision=decision.decision,
                    reasoning=decision.reasoning,
                ),
                embedding=data.get("embedding"),
            )
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
            embedding=self._resolve_embedding(content=content, embedding=data.get("embedding")),
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
            learning.embedding = self._resolve_embedding(
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
        normalized_query = str(query or "").strip()

        if project_id:
            decisions_query = decisions_query.filter(DecisionLog.project_id == project_id)
            learnings_query = learnings_query.filter(ProjectLearning.project_id == project_id)

        if normalized_query:
            lexical_preferences = (
                preferences_query.filter(
                    (UserPreference.category.contains(normalized_query))
                    | (UserPreference.key.contains(normalized_query))
                    | (UserPreference.value.contains(normalized_query))
                )
                .order_by(UserPreference.created_at.desc())
                .limit(20)
                .all()
            )
            lexical_decisions = (
                decisions_query.filter(
                    (DecisionLog.question.contains(normalized_query))
                    | (DecisionLog.decision.contains(normalized_query))
                    | (DecisionLog.reasoning.contains(normalized_query))
                )
                .order_by(DecisionLog.created_at.desc())
                .limit(20)
                .all()
            )
            lexical_learnings = (
                learnings_query.filter(ProjectLearning.content.contains(normalized_query))
                .order_by(ProjectLearning.created_at.desc())
                .limit(20)
                .all()
            )

            query_embedding = self._query_embedding(normalized_query)
            semantic_preferences = self._semantic_search_preferences(query_embedding=query_embedding)
            semantic_decisions = self._semantic_search_decisions(query_embedding=query_embedding, project_id=project_id)
            semantic_learnings = self._semantic_search_learnings(query_embedding=query_embedding, project_id=project_id)
            return {
                "preferences": self._merge_search_results(
                    semantic_items=semantic_preferences,
                    lexical_items=lexical_preferences,
                    serializer=self._preference_search_item,
                    identity=self._preference_search_identity,
                ),
                "decisions": self._merge_search_results(
                    semantic_items=semantic_decisions,
                    lexical_items=lexical_decisions,
                    serializer=self._decision_search_item,
                    identity=self._record_search_identity,
                ),
                "learnings": self._merge_search_results(
                    semantic_items=semantic_learnings,
                    lexical_items=lexical_learnings,
                    serializer=self._learning_search_item,
                    identity=self._record_search_identity,
                ),
            }

        return {
            "preferences": [item.to_dict() for item in preferences_query.order_by(UserPreference.created_at.desc()).limit(20).all()],
            "decisions": [item.to_dict() for item in decisions_query.order_by(DecisionLog.created_at.desc()).limit(20).all()],
            "learnings": [item.to_dict() for item in learnings_query.order_by(ProjectLearning.created_at.desc()).limit(20).all()],
        }

    def _resolve_embedding(self, *, content: str, embedding: Any) -> list[float] | None:
        if isinstance(embedding, list) and embedding:
            values = [float(item) for item in embedding]
            return values or None
        if not content or not settings.OPENAI_API_KEY.strip():
            return None
        return self._embed_text(content)

    def _query_embedding(self, query: str) -> list[float] | None:
        normalized_query = str(query or "").strip()
        if not normalized_query or not settings.OPENAI_API_KEY.strip():
            return None
        return self._embed_text(normalized_query)

    def _preference_embedding_text(self, *, category: str, key: str, value: str) -> str:
        return " ".join(part for part in [category.strip(), key.strip(), value.strip()] if part)

    def _decision_embedding_text(self, *, question: str, decision: str, reasoning: str) -> str:
        return " ".join(part for part in [question.strip(), decision.strip(), reasoning.strip()] if part)

    def _preference_search_item(
        self,
        preference: UserPreference,
        *,
        search_score: float | None = None,
        semantic_score: float | None = None,
        match_type: str | None = None,
    ) -> dict[str, Any]:
        return self._decorate_search_item(
            preference.to_dict(),
            search_score=search_score,
            semantic_score=semantic_score,
            match_type=match_type,
        )

    def _decision_search_item(
        self,
        decision: DecisionLog,
        *,
        search_score: float | None = None,
        semantic_score: float | None = None,
        match_type: str | None = None,
    ) -> dict[str, Any]:
        return self._decorate_search_item(
            decision.to_dict(),
            search_score=search_score,
            semantic_score=semantic_score,
            match_type=match_type,
        )

    def _learning_search_item(
        self,
        learning: ProjectLearning,
        *,
        search_score: float | None = None,
        semantic_score: float | None = None,
        match_type: str | None = None,
    ) -> dict[str, Any]:
        return self._decorate_search_item(
            learning.to_dict(),
            search_score=search_score,
            semantic_score=semantic_score,
            match_type=match_type,
        )

    def _decorate_search_item(
        self,
        payload: dict[str, Any],
        *,
        search_score: float | None,
        semantic_score: float | None,
        match_type: str | None,
    ) -> dict[str, Any]:
        item = dict(payload)
        if search_score is not None:
            item["searchScore"] = round(float(search_score), 6)
        if semantic_score is not None:
            item["semanticScore"] = round(float(semantic_score), 6)
        if match_type:
            item["matchType"] = match_type
        return item

    def _preference_search_identity(self, payload: dict[str, Any]) -> str:
        return f"{payload.get('category') or ''}::{payload.get('key') or ''}"

    def _record_search_identity(self, payload: dict[str, Any]) -> str:
        return str(payload.get("id") or "")

    def _merge_search_results(
        self,
        *,
        semantic_items: list[dict[str, Any]],
        lexical_items: list[Any],
        serializer,
        identity,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: dict[str, int] = {}

        for item in semantic_items:
            item_id = identity(item)
            if not item_id or item_id in seen:
                continue
            seen[item_id] = len(merged)
            merged.append(item)

        for record in lexical_items:
            item = serializer(record, search_score=1.0, match_type="lexical")
            item_id = identity(item)
            if not item_id:
                continue
            existing_index = seen.get(item_id)
            if existing_index is not None:
                existing = merged[existing_index]
                existing["matchType"] = "hybrid"
                existing["searchScore"] = round(max(float(existing.get("searchScore") or 0.0), 1.0), 6)
                continue
            seen[item_id] = len(merged)
            merged.append(item)

        return merged[:20]

    def _semantic_search_preferences(self, *, query_embedding: list[float] | None) -> list[dict[str, Any]]:
        if not query_embedding:
            return []

        ranked: list[tuple[float, UserPreference]] = []
        for preference in self.db.query(UserPreference).order_by(UserPreference.created_at.desc()).limit(200).all():
            embedding = preference.embedding
            if not isinstance(embedding, list) or not embedding:
                continue
            score = self._cosine_similarity(query_embedding, embedding)
            if score <= 0:
                continue
            ranked.append((score, preference))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            self._preference_search_item(
                preference,
                search_score=score,
                semantic_score=score,
                match_type="semantic",
            )
            for score, preference in ranked[:20]
        ]

    def _semantic_search_decisions(
        self,
        *,
        query_embedding: list[float] | None,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
        if not query_embedding:
            return []

        statement = self.db.query(DecisionLog)
        if project_id:
            statement = statement.filter(DecisionLog.project_id == project_id)

        ranked: list[tuple[float, DecisionLog]] = []
        for decision in statement.order_by(DecisionLog.created_at.desc()).limit(200).all():
            embedding = decision.embedding
            if not isinstance(embedding, list) or not embedding:
                continue
            score = self._cosine_similarity(query_embedding, embedding)
            if score <= 0:
                continue
            ranked.append((score, decision))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            self._decision_search_item(
                decision,
                search_score=score,
                semantic_score=score,
                match_type="semantic",
            )
            for score, decision in ranked[:20]
        ]

    def _semantic_search_learnings(
        self,
        *,
        query_embedding: list[float] | None,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
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
            self._learning_search_item(
                learning,
                search_score=score,
                semantic_score=score,
                match_type="semantic",
            )
            for score, learning in ranked[:20]
        ]

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
