"""Add v2 preview project/thread/run/memory tables

Revision ID: 002
Revises: 001
Create Date: 2026-03-25 13:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("repo_path", sa.String(1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("check_commands", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "project_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("reasoning_effort", sa.String(20), nullable=True),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("work_dir", sa.String(1000), nullable=True),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_rounds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "thread_run_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("path", sa.String(1000), nullable=True),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("category", "key", name="uq_user_preferences_category_key"),
    )

    op.create_table(
        "decision_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "project_learnings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_projects_status", "projects", ["status"])
    op.create_index("idx_projects_updated", "projects", ["updated_at"])
    op.create_index("idx_project_resources_project", "project_resources", ["project_id"])
    op.create_index("idx_project_resources_pinned", "project_resources", ["pinned"])
    op.create_index("idx_threads_project", "threads", ["project_id"])
    op.create_index("idx_threads_status", "threads", ["status"])
    op.create_index("idx_threads_updated", "threads", ["updated_at"])
    op.create_index("idx_messages_thread", "messages", ["thread_id"])
    op.create_index("idx_messages_role", "messages", ["role"])
    op.create_index("idx_runs_thread", "runs", ["thread_id"])
    op.create_index("idx_runs_message", "runs", ["message_id"])
    op.create_index("idx_runs_status", "runs", ["status"])
    op.create_index("idx_thread_run_artifacts_run", "thread_run_artifacts", ["run_id"])
    op.create_index("idx_user_preferences_category", "user_preferences", ["category"])
    op.create_index("idx_decision_log_project", "decision_log", ["project_id"])
    op.create_index("idx_project_learnings_project", "project_learnings", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_project_learnings_project", table_name="project_learnings")
    op.drop_index("idx_decision_log_project", table_name="decision_log")
    op.drop_index("idx_user_preferences_category", table_name="user_preferences")
    op.drop_index("idx_thread_run_artifacts_run", table_name="thread_run_artifacts")
    op.drop_index("idx_runs_status", table_name="runs")
    op.drop_index("idx_runs_message", table_name="runs")
    op.drop_index("idx_runs_thread", table_name="runs")
    op.drop_index("idx_messages_role", table_name="messages")
    op.drop_index("idx_messages_thread", table_name="messages")
    op.drop_index("idx_threads_updated", table_name="threads")
    op.drop_index("idx_threads_status", table_name="threads")
    op.drop_index("idx_threads_project", table_name="threads")
    op.drop_index("idx_project_resources_pinned", table_name="project_resources")
    op.drop_index("idx_project_resources_project", table_name="project_resources")
    op.drop_index("idx_projects_updated", table_name="projects")
    op.drop_index("idx_projects_status", table_name="projects")

    op.drop_table("project_learnings")
    op.drop_table("decision_log")
    op.drop_table("user_preferences")
    op.drop_table("thread_run_artifacts")
    op.drop_table("runs")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("project_resources")
    op.drop_table("projects")
