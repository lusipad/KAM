"""
AI代理模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, Integer, Boolean, DateTime, JSON, Table, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type

# 团队-代理关联表
team_agent_association = Table(
    'team_agents',
    Base.metadata,
    Column('team_id', uuid_type(), ForeignKey('agent_teams.id', ondelete='CASCADE'), primary_key=True),
    Column('agent_id', uuid_type(), ForeignKey('agents.id', ondelete='CASCADE'), primary_key=True),
)


class Agent(Base):
    __tablename__ = "agents"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    name = Column(String(200), nullable=False)
    role = Column(String(50), nullable=False)  # planner, decomposer, router, executor, specialist, validator, critic, synthesizer
    description = Column(Text)
    capabilities = Column(JSON, default=list)
    system_prompt = Column(Text)
    model = Column(String(100), default="gpt-4")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    tools = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    teams = relationship("AgentTeam", secondary=team_agent_association, back_populates="agents")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "capabilities": self.capabilities or [],
            "systemPrompt": self.system_prompt,
            "model": self.model,
            "temperature": self.temperature,
            "maxTokens": self.max_tokens,
            "tools": self.tools or [],
            "isActive": self.is_active,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class AgentTeam(Base):
    __tablename__ = "agent_teams"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    topology = Column(String(50), default="hierarchical")  # hierarchical, peer-to-peer, blackboard, pipeline
    coordinator_id = Column(uuid_type(), ForeignKey("agents.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    agents = relationship("Agent", secondary=team_agent_association, back_populates="teams")
    coordinator = relationship("Agent", foreign_keys=[coordinator_id])
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "topology": self.topology,
            "coordinatorId": str(self.coordinator_id) if self.coordinator_id else None,
            "agents": [agent.to_dict() for agent in self.agents] if self.agents else [],
            "isActive": self.is_active,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
