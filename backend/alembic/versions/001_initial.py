"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 启用pgvector扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # notes表
    op.create_table(
        'notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('title', sa.String(500), nullable=False, default=""),
        sa.Column('content', sa.Text, nullable=False, default=""),
        sa.Column('content_type', sa.String(20), default="markdown"),
        sa.Column('path', sa.String(1000), nullable=False),
        sa.Column('version', sa.Integer, default=1),
        sa.Column('metadata', sa.JSON, default=dict),
        sa.Column('stats', sa.JSON, default=dict),
        sa.Column('content_vector', sa.NullType),  # vector类型
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # links表
    op.create_table(
        'links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('source_note_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_note_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('link_type', sa.String(20), default="wiki"),
        sa.Column('context', sa.JSON, default=dict),
        sa.Column('is_resolved', sa.Boolean, default=True),
        sa.Column('is_embed', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # memories表
    op.create_table(
        'memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', sa.String(100), default="default"),
        sa.Column('memory_type', sa.String(20), nullable=False),
        sa.Column('category', sa.String(100)),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('content_vector', sa.NullType),  # vector类型
        sa.Column('summary', sa.Text),
        sa.Column('summary_vector', sa.NullType),  # vector类型
        sa.Column('importance_score', sa.Float, default=0.5),
        sa.Column('confidence_score', sa.Float, default=0.8),
        sa.Column('access_count', sa.Integer, default=0),
        sa.Column('metadata', sa.JSON, default=dict),
        sa.Column('context', sa.JSON, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_accessed', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # agents表
    op.create_table(
        'agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('capabilities', sa.JSON, default=list),
        sa.Column('system_prompt', sa.Text),
        sa.Column('model', sa.String(100), default="gpt-4"),
        sa.Column('temperature', sa.Float, default=0.7),
        sa.Column('max_tokens', sa.Integer, default=2000),
        sa.Column('tools', sa.JSON, default=list),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # agent_teams表
    op.create_table(
        'agent_teams',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('topology', sa.String(50), default="hierarchical"),
        sa.Column('coordinator_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # team_agents关联表
    op.create_table(
        'team_agents',
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_teams.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), primary_key=True),
    )
    
    # tasks表
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_teams.id'), nullable=True),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('goal', sa.Text),
        sa.Column('constraints', sa.JSON, default=list),
        sa.Column('status', sa.String(20), default="pending"),
        sa.Column('priority', sa.Integer, default=5),
        sa.Column('result', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )
    
    # subtasks表
    op.create_table(
        'subtasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('complexity', sa.Integer, default=5),
        sa.Column('required_capabilities', sa.JSON, default=list),
        sa.Column('assigned_agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('dependencies', sa.JSON, default=list),
        sa.Column('status', sa.String(20), default="pending"),
        sa.Column('expected_output', sa.Text),
        sa.Column('actual_output', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )
    
    # ado_configs表
    op.create_table(
        'ado_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('server_url', sa.String(500), nullable=False),
        sa.Column('collection', sa.String(200), default="DefaultCollection"),
        sa.Column('project', sa.String(200), nullable=False),
        sa.Column('auth_type', sa.String(20), default="pat"),
        sa.Column('credentials', sa.JSON, default=dict),
        sa.Column('scopes', sa.JSON, default=list),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # conversations表
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('title', sa.String(500), default="新对话"),
        sa.Column('context', sa.JSON, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # messages表
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('metadata', sa.JSON, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # 创建索引
    op.create_index('idx_notes_updated', 'notes', ['updated_at'])
    op.create_index('idx_links_source', 'links', ['source_note_id'])
    op.create_index('idx_links_target', 'links', ['target_note_id'])
    op.create_index('idx_memories_user', 'memories', ['user_id'])
    op.create_index('idx_memories_type', 'memories', ['memory_type'])
    op.create_index('idx_memories_importance', 'memories', ['importance_score'])
    op.create_index('idx_tasks_team', 'tasks', ['team_id'])
    op.create_index('idx_messages_conversation', 'messages', ['conversation_id'])


def downgrade() -> None:
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('ado_configs')
    op.drop_table('subtasks')
    op.drop_table('tasks')
    op.drop_table('team_agents')
    op.drop_table('agent_teams')
    op.drop_table('agents')
    op.drop_table('memories')
    op.drop_table('links')
    op.drop_table('notes')
