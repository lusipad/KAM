import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now(UTC)


def serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    repo_path: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    threads: Mapped[list["Thread"]] = relationship(back_populates="project")
    memories: Mapped[list["Memory"]] = relationship(back_populates="project")
    watchers: Mapped[list["Watcher"]] = relationship(back_populates="project")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "repoPath": self.repo_path,
            "createdAt": serialize_datetime(self.created_at),
        }


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    external_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    project: Mapped["Project"] = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["Run"]] = relationship(
        back_populates="thread",
        order_by="Run.created_at",
        cascade="all, delete-orphan",
    )

    def to_summary_dict(self) -> dict[str, Any]:
        state = sa_inspect(self)
        runs = [] if "runs" in state.unloaded else list(self.runs)
        project = None if "project" in state.unloaded else self.project
        latest_run = runs[-1] if runs else None
        has_active_run = any(run.status in {"pending", "running"} for run in runs)
        return {
            "id": self.id,
            "projectId": self.project_id,
            "title": self.title,
            "externalRef": self.external_ref,
            "createdAt": serialize_datetime(self.created_at),
            "updatedAt": serialize_datetime(self.updated_at),
            "project": project.to_dict() if project else None,
            "hasActiveRun": has_active_run,
            "latestRunStatus": latest_run.status if latest_run else None,
            "latestRunSummary": latest_run.result_summary if latest_run else None,
        }

    def to_detail_dict(self) -> dict[str, Any]:
        state = sa_inspect(self)
        messages = [] if "messages" in state.unloaded else [message.to_dict() for message in self.messages]
        runs = [] if "runs" in state.unloaded else [run.to_dict() for run in self.runs]
        return {
            **self.to_summary_dict(),
            "messages": messages,
            "runs": runs,
        }


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    thread: Mapped["Thread"] = relationship(back_populates="messages")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "threadId": self.thread_id,
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata_ or {},
            "createdAt": serialize_datetime(self.created_at),
        }


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"))
    agent: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    task: Mapped[str] = mapped_column(Text)
    result_summary: Mapped[str] = mapped_column(Text, nullable=True)
    changed_files: Mapped[list[str]] = mapped_column(JSON, nullable=True)
    check_passed: Mapped[bool] = mapped_column(Boolean, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    worktree_path: Mapped[str] = mapped_column(String(500), nullable=True)
    adopted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_output: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    thread: Mapped["Thread"] = relationship(back_populates="runs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "threadId": self.thread_id,
            "agent": self.agent,
            "status": self.status,
            "task": self.task,
            "resultSummary": self.result_summary,
            "changedFiles": self.changed_files or [],
            "checkPassed": self.check_passed,
            "durationMs": self.duration_ms,
            "worktreePath": self.worktree_path,
            "adoptedAt": serialize_datetime(self.adopted_at),
            "rawOutput": self.raw_output or "",
            "createdAt": serialize_datetime(self.created_at),
        }


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=True)
    scope: Mapped[str] = mapped_column(String(20), default="project")
    category: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0)
    superseded_by: Mapped[str] = mapped_column(String(12), nullable=True)
    source_thread_id: Mapped[str] = mapped_column(String(12), nullable=True)
    source_message_id: Mapped[str] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    project: Mapped["Project"] = relationship(back_populates="memories")

    __table_args__ = (
        Index("ix_memory_project_category", "project_id", "category"),
        Index("ix_memory_relevance", "relevance_score"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "scope": self.scope,
            "category": self.category,
            "content": self.content,
            "rationale": self.rationale,
            "relevanceScore": self.relevance_score,
            "supersededBy": self.superseded_by,
            "sourceThreadId": self.source_thread_id,
            "sourceMessageId": self.source_message_id,
            "createdAt": serialize_datetime(self.created_at),
            "lastAccessedAt": serialize_datetime(self.last_accessed_at),
        }


class Watcher(Base):
    __tablename__ = "watchers"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    schedule_type: Mapped[str] = mapped_column(String(20))
    schedule_value: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="active")
    auto_action_level: Mapped[int] = mapped_column(Integer, default=1)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    project: Mapped["Project"] = relationship(back_populates="watchers")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "name": self.name,
            "sourceType": self.source_type,
            "config": self.config,
            "scheduleType": self.schedule_type,
            "scheduleValue": self.schedule_value,
            "status": self.status,
            "autoActionLevel": self.auto_action_level,
            "lastRunAt": serialize_datetime(self.last_run_at),
            "lastState": self.last_state or {},
            "createdAt": serialize_datetime(self.created_at),
        }


class WatcherEvent(Base):
    __tablename__ = "watcher_events"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    watcher_id: Mapped[str] = mapped_column(ForeignKey("watchers.id"))
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    watcher: Mapped["Watcher"] = relationship()
    thread: Mapped["Thread"] = relationship()

    def to_dict(self) -> dict[str, Any]:
        state = sa_inspect(self)
        watcher = None if "watcher" in state.unloaded else self.watcher
        return {
            "id": self.id,
            "watcherId": self.watcher_id,
            "threadId": self.thread_id,
            "eventType": self.event_type,
            "title": self.title,
            "summary": self.summary,
            "rawData": self.raw_data,
            "actions": self.actions or [],
            "status": self.status,
            "createdAt": serialize_datetime(self.created_at),
            "watcher": watcher.to_dict() if watcher else None,
        }
