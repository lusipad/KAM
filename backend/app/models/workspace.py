"""
Lite 任务与 Agent Run 模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class TaskCard(Base):
    __tablename__ = "task_cards"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="inbox")  # inbox, ready, running, review, done, archived
    priority = Column(String(20), default="medium")  # low, medium, high
    tags = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    refs = relationship("TaskRef", back_populates="task", cascade="all, delete-orphan", order_by="TaskRef.created_at")
    snapshots = relationship(
        "ContextSnapshot",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ContextSnapshot.created_at.desc()",
    )
    runs = relationship("AgentRun", back_populates="task", cascade="all, delete-orphan", order_by="AgentRun.created_at.desc()")
    autonomy_sessions = relationship(
        "AutonomySession",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="AutonomySession.created_at.desc()",
    )

    __table_args__ = (
        Index("idx_task_cards_status", "status"),
        Index("idx_task_cards_updated", "updated_at"),
    )

    def to_dict(self, include_relations: bool = True):
        data = {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "tags": self.tags or [],
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_relations:
            data["refs"] = [ref.to_dict() for ref in self.refs] if self.refs else []
            data["runs"] = [run.to_dict(include_artifacts=False) for run in self.runs] if self.runs else []
            data["latestSnapshot"] = self.snapshots[0].to_dict(include_data=False) if self.snapshots else None

        return data


class TaskRef(Base):
    __tablename__ = "task_refs"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    task_id = Column(uuid_type(), ForeignKey("task_cards.id", ondelete="CASCADE"), nullable=False)
    ref_type = Column(String(50), nullable=False)  # repo-path, file, url, work-item, pr, doc
    label = Column(String(200), nullable=False)
    value = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    task = relationship("TaskCard", back_populates="refs")

    __table_args__ = (
        Index("idx_task_refs_task", "task_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "taskId": str(self.task_id),
            "type": self.ref_type,
            "label": self.label,
            "value": self.value,
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class ContextSnapshot(Base):
    __tablename__ = "context_snapshots"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    task_id = Column(uuid_type(), ForeignKey("task_cards.id", ondelete="CASCADE"), nullable=False)
    summary = Column(Text, default="")
    data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    task = relationship("TaskCard", back_populates="snapshots")

    __table_args__ = (
        Index("idx_context_snapshots_task", "task_id"),
    )

    def to_dict(self, include_data: bool = True):
        payload = {
            "id": str(self.id),
            "taskId": str(self.task_id),
            "summary": self.summary,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
        if include_data:
            payload["data"] = self.data or {}
        return payload


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    task_id = Column(uuid_type(), ForeignKey("task_cards.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(100), nullable=False)
    agent_type = Column(String(50), default="custom")  # codex, claude-code, custom
    status = Column(String(20), default="planned")  # planned, queued, running, completed, failed, canceled
    workdir = Column(String(1000), nullable=True)
    prompt = Column(Text, default="")
    command = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("TaskCard", back_populates="runs")
    artifacts = relationship(
        "RunArtifact",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunArtifact.created_at",
    )

    __table_args__ = (
        Index("idx_agent_runs_task", "task_id"),
        Index("idx_agent_runs_status", "status"),
    )

    def to_dict(self, include_artifacts: bool = True):
        data = {
            "id": str(self.id),
            "taskId": str(self.task_id),
            "agentName": self.agent_name,
            "agentType": self.agent_type,
            "status": self.status,
            "workdir": self.workdir,
            "prompt": self.prompt,
            "command": self.command,
            "errorMessage": self.error_message,
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_artifacts:
            data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts] if self.artifacts else []
        return data


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    run_id = Column(uuid_type(), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(50), nullable=False)  # prompt, context, log, patch, summary
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    path = Column(String(1000), nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    run = relationship("AgentRun", back_populates="artifacts")

    __table_args__ = (
        Index("idx_run_artifacts_run", "run_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "runId": str(self.run_id),
            "type": self.artifact_type,
            "title": self.title,
            "content": self.content,
            "path": self.path,
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class AutonomySession(Base):
    __tablename__ = "autonomy_sessions"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    task_id = Column(uuid_type(), ForeignKey("task_cards.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    objective = Column(Text, default="")
    status = Column(String(20), default="draft")  # draft, running, completed, failed, interrupted
    repo_path = Column(String(1000), nullable=True)
    primary_agent_name = Column(String(100), nullable=False)
    primary_agent_type = Column(String(50), default="codex")
    primary_agent_command = Column(Text, nullable=True)
    max_iterations = Column(Integer, default=3)
    current_iteration = Column(Integer, default=0)
    interruption_count = Column(Integer, default=0)
    success_criteria = Column(Text, default="")
    check_commands = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("TaskCard", back_populates="autonomy_sessions")
    cycles = relationship(
        "AutonomyCycle",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AutonomyCycle.iteration.desc()",
    )

    __table_args__ = (
        Index("idx_autonomy_sessions_task", "task_id"),
        Index("idx_autonomy_sessions_status", "status"),
    )

    def to_dict(self, include_cycles: bool = True):
        data = {
            "id": str(self.id),
            "taskId": str(self.task_id),
            "title": self.title,
            "objective": self.objective,
            "status": self.status,
            "repoPath": self.repo_path,
            "primaryAgentName": self.primary_agent_name,
            "primaryAgentType": self.primary_agent_type,
            "primaryAgentCommand": self.primary_agent_command,
            "maxIterations": self.max_iterations,
            "currentIteration": self.current_iteration,
            "interruptionCount": self.interruption_count,
            "successCriteria": self.success_criteria,
            "checkCommands": self.check_commands or [],
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_cycles:
            data["cycles"] = [cycle.to_dict() for cycle in self.cycles] if self.cycles else []
        else:
            data["latestCycle"] = self.cycles[0].to_dict() if self.cycles else None
        return data


class AutonomyCycle(Base):
    __tablename__ = "autonomy_cycles"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    session_id = Column(uuid_type(), ForeignKey("autonomy_sessions.id", ondelete="CASCADE"), nullable=False)
    iteration = Column(Integer, nullable=False)
    status = Column(String(20), default="planned")  # running, checking, passed, failed, interrupted
    worker_run_id = Column(uuid_type(), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    feedback_summary = Column(Text, default="")
    check_results = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    session = relationship("AutonomySession", back_populates="cycles")
    worker_run = relationship("AgentRun")

    __table_args__ = (
        Index("idx_autonomy_cycles_session", "session_id"),
        Index("idx_autonomy_cycles_status", "status"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "sessionId": str(self.session_id),
            "iteration": self.iteration,
            "status": self.status,
            "workerRunId": str(self.worker_run_id) if self.worker_run_id else None,
            "workerRun": self.worker_run.to_dict(include_artifacts=False) if self.worker_run else None,
            "feedbackSummary": self.feedback_summary,
            "checkResults": self.check_results or [],
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }
