from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, MetaData, String, Table, Text

LEGACY_TABLE_NAMES = [
    'task_cards',
    'task_refs',
    'context_snapshots',
    'agent_runs',
    'run_artifacts',
    'autonomy_sessions',
    'autonomy_cycles',
]


def build_legacy_metadata() -> MetaData:
    metadata = MetaData()

    Table(
        'task_cards',
        metadata,
        Column('id', String(36), primary_key=True),
        Column('title', String(200), nullable=False),
        Column('description', Text, nullable=False, default=''),
        Column('status', String(20), nullable=False, default='inbox'),
        Column('priority', String(20), nullable=False, default='medium'),
        Column('tags', JSON, nullable=False, default=list),
        Column('metadata', JSON, nullable=False, default=dict),
        Column('created_at', DateTime(timezone=True), default=datetime.utcnow),
        Column('updated_at', DateTime(timezone=True), default=datetime.utcnow),
    )

    Table(
        'task_refs',
        metadata,
        Column('id', String(36), primary_key=True),
        Column('task_id', String(36), ForeignKey('task_cards.id', ondelete='CASCADE'), nullable=False),
        Column('ref_type', String(50), nullable=False),
        Column('label', String(200), nullable=False),
        Column('value', Text, nullable=False),
        Column('metadata', JSON, nullable=False, default=dict),
        Column('created_at', DateTime(timezone=True), default=datetime.utcnow),
        Index('idx_task_refs_task', 'task_id'),
    )

    Table(
        'context_snapshots',
        metadata,
        Column('id', String(36), primary_key=True),
        Column('task_id', String(36), ForeignKey('task_cards.id', ondelete='CASCADE'), nullable=False),
        Column('summary', Text, nullable=False, default=''),
        Column('data', JSON, nullable=False, default=dict),
        Column('created_at', DateTime(timezone=True), default=datetime.utcnow),
        Index('idx_context_snapshots_task', 'task_id'),
    )

    Table(
        'agent_runs',
        metadata,
        Column('id', String(36), primary_key=True),
        Column('task_id', String(36), ForeignKey('task_cards.id', ondelete='CASCADE'), nullable=False),
        Column('agent_name', String(100), nullable=False),
        Column('agent_type', String(50), nullable=False, default='custom'),
        Column('status', String(20), nullable=False, default='planned'),
        Column('workdir', String(1000), nullable=True),
        Column('prompt', Text, nullable=False, default=''),
        Column('command', Text, nullable=True),
        Column('error_message', Text, nullable=True),
        Column('metadata', JSON, nullable=False, default=dict),
        Column('created_at', DateTime(timezone=True), default=datetime.utcnow),
        Column('started_at', DateTime(timezone=True), nullable=True),
        Column('completed_at', DateTime(timezone=True), nullable=True),
        Index('idx_agent_runs_task', 'task_id'),
        Index('idx_agent_runs_status', 'status'),
    )

    Table(
        'run_artifacts',
        metadata,
        Column('id', String(36), primary_key=True),
        Column('run_id', String(36), ForeignKey('agent_runs.id', ondelete='CASCADE'), nullable=False),
        Column('artifact_type', String(50), nullable=False),
        Column('title', String(200), nullable=False),
        Column('content', Text, nullable=False, default=''),
        Column('path', String(1000), nullable=True),
        Column('metadata', JSON, nullable=False, default=dict),
        Column('created_at', DateTime(timezone=True), default=datetime.utcnow),
        Index('idx_run_artifacts_run', 'run_id'),
    )

    Table(
        'autonomy_sessions',
        metadata,
        Column('id', String(36), primary_key=True),
        Column('task_id', String(36), ForeignKey('task_cards.id', ondelete='CASCADE'), nullable=False),
        Column('title', String(200), nullable=False),
        Column('objective', Text, nullable=False, default=''),
        Column('status', String(20), nullable=False, default='draft'),
        Column('repo_path', String(1000), nullable=True),
        Column('primary_agent_name', String(100), nullable=False),
        Column('primary_agent_type', String(50), nullable=False, default='codex'),
        Column('primary_agent_command', Text, nullable=True),
        Column('max_iterations', Integer, nullable=False, default=3),
        Column('current_iteration', Integer, nullable=False, default=0),
        Column('interruption_count', Integer, nullable=False, default=0),
        Column('success_criteria', Text, nullable=False, default=''),
        Column('check_commands', JSON, nullable=False, default=list),
        Column('metadata', JSON, nullable=False, default=dict),
        Column('created_at', DateTime(timezone=True), default=datetime.utcnow),
        Column('updated_at', DateTime(timezone=True), default=datetime.utcnow),
        Column('completed_at', DateTime(timezone=True), nullable=True),
        Index('idx_autonomy_sessions_task', 'task_id'),
        Index('idx_autonomy_sessions_status', 'status'),
    )

    Table(
        'autonomy_cycles',
        metadata,
        Column('id', String(36), primary_key=True),
        Column('session_id', String(36), ForeignKey('autonomy_sessions.id', ondelete='CASCADE'), nullable=False),
        Column('iteration', Integer, nullable=False),
        Column('status', String(20), nullable=False, default='planned'),
        Column('worker_run_id', String(36), ForeignKey('agent_runs.id', ondelete='SET NULL'), nullable=True),
        Column('feedback_summary', Text, nullable=False, default=''),
        Column('check_results', JSON, nullable=False, default=list),
        Column('metadata', JSON, nullable=False, default=dict),
        Column('created_at', DateTime(timezone=True), default=datetime.utcnow),
        Column('completed_at', DateTime(timezone=True), nullable=True),
        Index('idx_autonomy_cycles_session', 'session_id'),
        Index('idx_autonomy_cycles_status', 'status'),
    )

    return metadata


def create_legacy_tables(engine) -> None:
    metadata = build_legacy_metadata()
    metadata.create_all(bind=engine)


def drop_legacy_tables(engine) -> None:
    metadata = build_legacy_metadata()
    metadata.drop_all(bind=engine, checkfirst=True)


def legacy_tables_present(table_names: Iterable[str]) -> bool:
    current = set(table_names)
    return any(name in current for name in LEGACY_TABLE_NAMES)
