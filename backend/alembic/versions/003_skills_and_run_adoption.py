"""Add skills table and run adoption timestamp

Revision ID: 003
Revises: 002
Create Date: 2026-03-26 11:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _uuid_type():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return sa.String(36)
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    uuid_type = _uuid_type()
    op.add_column("runs", sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "skills",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("project_id", uuid_type, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("agent", sa.String(50), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(50), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_skills_scope", "skills", ["scope"])
    op.create_index("idx_skills_project", "skills", ["project_id"])
    op.create_unique_constraint("uq_skills_scope_project_name", "skills", ["scope", "project_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_skills_scope_project_name", "skills", type_="unique")
    op.drop_index("idx_skills_project", table_name="skills")
    op.drop_index("idx_skills_scope", table_name="skills")
    op.drop_table("skills")
    op.drop_column("runs", "adopted_at")
