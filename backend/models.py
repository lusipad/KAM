import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now(UTC)


def serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    repo_path: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    refs: Mapped[list["TaskRef"]] = relationship(
        back_populates="task",
        order_by="TaskRef.created_at",
        cascade="all, delete-orphan",
    )
    snapshots: Mapped[list["ContextSnapshot"]] = relationship(
        back_populates="task",
        order_by="ContextSnapshot.created_at",
        cascade="all, delete-orphan",
    )
    review_compares: Mapped[list["ReviewCompare"]] = relationship(
        back_populates="task",
        order_by="ReviewCompare.created_at",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["TaskRun"]] = relationship(
        back_populates="task_rel",
        order_by="TaskRun.created_at",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "repoPath": self.repo_path,
            "status": self.status,
            "priority": self.priority,
            "labels": self.labels or [],
            "metadata": self.metadata_ or {},
            "archivedAt": serialize_datetime(self.archived_at),
            "createdAt": serialize_datetime(self.created_at),
            "updatedAt": serialize_datetime(self.updated_at),
        }

    def to_detail_dict(self) -> dict[str, Any]:
        return {
            **self.to_dict(),
            "refs": [ref.to_dict() for ref in self.refs],
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
        }


class TaskRef(Base):
    __tablename__ = "task_refs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    kind: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    task: Mapped["Task"] = relationship(back_populates="refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "taskId": self.task_id,
            "kind": self.kind,
            "label": self.label,
            "value": self.value,
            "metadata": self.metadata_ or {},
            "createdAt": serialize_datetime(self.created_at),
        }


class ContextSnapshot(Base):
    __tablename__ = "context_snapshots"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    summary: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    focus: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    task: Mapped["Task"] = relationship(back_populates="snapshots")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "taskId": self.task_id,
            "summary": self.summary,
            "content": self.content,
            "focus": self.focus,
            "createdAt": serialize_datetime(self.created_at),
        }


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
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

    task_rel: Mapped["Task"] = relationship(back_populates="runs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "taskId": self.task_id,
            "threadId": None,
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


class TaskRunArtifact(Base):
    __tablename__ = "task_run_artifacts"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"))
    type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "runId": self.task_run_id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata_ or {},
            "createdAt": serialize_datetime(self.created_at),
        }


class ReviewCompare(Base):
    __tablename__ = "review_compares"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    title: Mapped[str] = mapped_column(String(200))
    run_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    task: Mapped["Task"] = relationship(back_populates="review_compares")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "taskId": self.task_id,
            "title": self.title,
            "runIds": self.run_ids or [],
            "summary": self.summary,
            "createdAt": serialize_datetime(self.created_at),
        }
