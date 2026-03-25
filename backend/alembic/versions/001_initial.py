"""Lite core initial migration

Revision ID: 001
Revises:
Create Date: 2026-03-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="inbox"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "task_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref_type", sa.String(50), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "context_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("agent_type", sa.String(50), nullable=False, server_default="custom"),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("workdir", sa.String(1000), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "run_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("path", sa.String(1000), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_task_cards_status", "task_cards", ["status"])
    op.create_index("idx_task_cards_updated", "task_cards", ["updated_at"])
    op.create_index("idx_task_refs_task", "task_refs", ["task_id"])
    op.create_index("idx_context_snapshots_task", "context_snapshots", ["task_id"])
    op.create_index("idx_agent_runs_task", "agent_runs", ["task_id"])
    op.create_index("idx_agent_runs_status", "agent_runs", ["status"])
    op.create_index("idx_run_artifacts_run", "run_artifacts", ["run_id"])


def downgrade() -> None:
    op.drop_index("idx_run_artifacts_run", table_name="run_artifacts")
    op.drop_index("idx_agent_runs_status", table_name="agent_runs")
    op.drop_index("idx_agent_runs_task", table_name="agent_runs")
    op.drop_index("idx_context_snapshots_task", table_name="context_snapshots")
    op.drop_index("idx_task_refs_task", table_name="task_refs")
    op.drop_index("idx_task_cards_updated", table_name="task_cards")
    op.drop_index("idx_task_cards_status", table_name="task_cards")
    op.drop_table("run_artifacts")
    op.drop_table("agent_runs")
    op.drop_table("context_snapshots")
    op.drop_table("task_refs")
    op.drop_table("task_cards")
