"""Add missing run_artifacts table to Alembic history.

Revision ID: 003_run_artifacts_schema_fix
Revises: 002_task_harness_schema
Create Date: 2026-04-03 09:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "003_run_artifacts_schema_fix"
down_revision = "002_task_harness_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "run_artifacts" in inspector.get_table_names():
        return

    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("run_id", sa.String(length=12), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "run_artifacts" in inspector.get_table_names():
        op.drop_table("run_artifacts")
