"""V3 initial schema.

Revision ID: 001_v3_initial
Revises:
Create Date: 2026-03-27 15:50:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "001_v3_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("repo_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("project_id", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("external_ref", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("thread_id", sa.String(length=12), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("thread_id", sa.String(length=12), nullable=False),
        sa.Column("agent", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("changed_files", sa.JSON(), nullable=True),
        sa.Column("check_passed", sa.Boolean(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("worktree_path", sa.String(length=500), nullable=True),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("project_id", sa.String(length=12), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("superseded_by", sa.String(length=12), nullable=True),
        sa.Column("source_thread_id", sa.String(length=12), nullable=True),
        sa.Column("source_message_id", sa.String(length=12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_project_category", "memories", ["project_id", "category"], unique=False)
    op.create_index("ix_memory_relevance", "memories", ["relevance_score"], unique=False)

    op.create_table(
        "watchers",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("project_id", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("schedule_type", sa.String(length=20), nullable=False),
        sa.Column("schedule_value", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("auto_action_level", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "watcher_events",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("watcher_id", sa.String(length=12), nullable=False),
        sa.Column("thread_id", sa.String(length=12), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"]),
        sa.ForeignKeyConstraint(["watcher_id"], ["watchers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("watcher_events")
    op.drop_table("watchers")
    op.drop_index("ix_memory_relevance", table_name="memories")
    op.drop_index("ix_memory_project_category", table_name="memories")
    op.drop_table("memories")
    op.drop_table("runs")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("projects")
