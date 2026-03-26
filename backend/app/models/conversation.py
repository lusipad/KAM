"""
KAM v2 对话与 Run 模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class Thread(Base):
    __tablename__ = "threads"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    project_id = Column(uuid_type(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="threads")
    messages = relationship(
        "Message",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    runs = relationship(
        "Run",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Run.created_at.desc()",
    )

    __table_args__ = (
        Index("idx_threads_project", "project_id"),
        Index("idx_threads_status", "status"),
        Index("idx_threads_updated", "updated_at"),
    )

    def to_dict(self, include_relations: bool = False, include_runs: bool = False):
        data = {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "title": self.title,
            "status": self.status,
            "messageCount": len(self.messages or []),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_relations:
            data["messages"] = [message.to_dict(include_runs=True) for message in self.messages] if self.messages else []
            data["latestRun"] = self.runs[0].to_dict(include_artifacts=False) if self.runs else None
            if include_runs:
                data["runs"] = [run.to_dict(include_artifacts=False) for run in self.runs] if self.runs else []
        return data


class Message(Base):
    __tablename__ = "messages"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    thread_id = Column(uuid_type(), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    thread = relationship("Thread", back_populates="messages")
    runs = relationship(
        "Run",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="Run.created_at.desc()",
    )

    __table_args__ = (
        Index("idx_messages_thread", "thread_id"),
        Index("idx_messages_role", "role"),
    )

    def to_dict(self, include_runs: bool = False):
        data = {
            "id": str(self.id),
            "threadId": str(self.thread_id),
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
        if include_runs:
            data["runs"] = [run.to_dict(include_artifacts=False) for run in self.runs] if self.runs else []
        return data


class Run(Base):
    __tablename__ = "runs"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    thread_id = Column(uuid_type(), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(uuid_type(), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    agent = Column(String(50), nullable=False)
    model = Column(String(100), nullable=True)
    reasoning_effort = Column(String(20), nullable=True)
    command = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    work_dir = Column(String(1000), nullable=True)
    round = Column(Integer, default=1)
    max_rounds = Column(Integer, default=5)
    duration_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    adopted_at = Column(DateTime(timezone=True), nullable=True)

    thread = relationship("Thread", back_populates="runs")
    message = relationship("Message", back_populates="runs")
    artifacts = relationship(
        "ThreadRunArtifact",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ThreadRunArtifact.created_at",
    )

    __table_args__ = (
        Index("idx_runs_thread", "thread_id"),
        Index("idx_runs_message", "message_id"),
        Index("idx_runs_status", "status"),
    )

    def to_dict(self, include_artifacts: bool = True):
        data = {
            "id": str(self.id),
            "threadId": str(self.thread_id),
            "messageId": str(self.message_id) if self.message_id else None,
            "agent": self.agent,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort,
            "command": self.command,
            "status": self.status,
            "workDir": self.work_dir,
            "round": self.round,
            "maxRounds": self.max_rounds,
            "durationMs": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "adoptedAt": self.adopted_at.isoformat() if self.adopted_at else None,
        }
        if include_artifacts:
            data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts] if self.artifacts else []
        return data


class ThreadRunArtifact(Base):
    __tablename__ = "thread_run_artifacts"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    run_id = Column(uuid_type(), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    path = Column(String(1000), nullable=True)
    round = Column(Integer, default=1)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    run = relationship("Run", back_populates="artifacts")

    __table_args__ = (
        Index("idx_thread_run_artifacts_run", "run_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "runId": str(self.run_id),
            "type": self.artifact_type,
            "title": self.title,
            "content": self.content,
            "path": self.path,
            "round": self.round,
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
