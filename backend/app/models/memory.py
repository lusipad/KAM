"""
KAM v2 记忆模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    category = Column(String(50), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)
    source_thread_id = Column(uuid_type(), ForeignKey("threads.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_user_preferences_category", "category"),
        UniqueConstraint("category", "key", name="uq_user_preferences_category_key"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "sourceThreadId": str(self.source_thread_id) if self.source_thread_id else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class DecisionLog(Base):
    __tablename__ = "decision_log"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    project_id = Column(uuid_type(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    question = Column(Text, nullable=False)
    decision = Column(Text, nullable=False)
    reasoning = Column(Text, default="")
    embedding = Column(JSON, nullable=True)
    source_thread_id = Column(uuid_type(), ForeignKey("threads.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    project = relationship("Project", back_populates="decisions")

    __table_args__ = (
        Index("idx_decision_log_project", "project_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id) if self.project_id else None,
            "question": self.question,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "sourceThreadId": str(self.source_thread_id) if self.source_thread_id else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class ProjectLearning(Base):
    __tablename__ = "project_learnings"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    project_id = Column(uuid_type(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)
    source_thread_id = Column(uuid_type(), ForeignKey("threads.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    project = relationship("Project", back_populates="learnings")

    __table_args__ = (
        Index("idx_project_learnings_project", "project_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "content": self.content,
            "embedding": self.embedding,
            "sourceThreadId": str(self.source_thread_id) if self.source_thread_id else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
