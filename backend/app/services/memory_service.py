"""
KAM v2 记忆服务
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

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

    def list_learnings(self, project_id: str | None = None, query: str | None = None) -> list[ProjectLearning]:
        statement = self.db.query(ProjectLearning)
        if project_id:
            statement = statement.filter(ProjectLearning.project_id == project_id)
        if query:
            statement = statement.filter(ProjectLearning.content.contains(query))
        return statement.order_by(ProjectLearning.created_at.desc()).all()

    def create_learning(self, data: dict[str, Any]) -> ProjectLearning:
        learning = ProjectLearning(
            project_id=data.get("projectId") or data.get("project_id"),
            content=data["content"],
            embedding=data.get("embedding"),
            source_thread_id=data.get("sourceThreadId") or data.get("source_thread_id"),
        )
        self.db.add(learning)
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

        return {
            "preferences": [item.to_dict() for item in preferences_query.order_by(UserPreference.created_at.desc()).limit(20).all()],
            "decisions": [item.to_dict() for item in decisions_query.order_by(DecisionLog.created_at.desc()).limit(20).all()],
            "learnings": [item.to_dict() for item in learnings_query.order_by(ProjectLearning.created_at.desc()).limit(20).all()],
        }
