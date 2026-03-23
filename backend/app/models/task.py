"""
任务模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    team_id = Column(uuid_type(), ForeignKey("agent_teams.id"), nullable=True)
    description = Column(Text, nullable=False)
    goal = Column(Text)
    constraints = Column(JSON, default=list)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    priority = Column(Integer, default=5)
    result = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关系
    team = relationship("AgentTeam")
    subtasks = relationship("SubTask", back_populates="task", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "teamId": str(self.team_id) if self.team_id else None,
            "description": self.description,
            "goal": self.goal,
            "constraints": self.constraints or [],
            "status": self.status,
            "priority": self.priority,
            "result": self.result,
            "subtasks": [st.to_dict() for st in self.subtasks] if self.subtasks else [],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }


class SubTask(Base):
    __tablename__ = "subtasks"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    task_id = Column(uuid_type(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    complexity = Column(Integer, default=5)
    required_capabilities = Column(JSON, default=list)
    assigned_agent_id = Column(uuid_type(), ForeignKey("agents.id"), nullable=True)
    dependencies = Column(JSON, default=list)
    status = Column(String(20), default="pending")
    expected_output = Column(Text)
    actual_output = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关系
    task = relationship("Task", back_populates="subtasks")
    assigned_agent = relationship("Agent")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "taskId": str(self.task_id),
            "description": self.description,
            "complexity": self.complexity,
            "requiredCapabilities": self.required_capabilities or [],
            "assignedAgentId": str(self.assigned_agent_id) if self.assigned_agent_id else None,
            "dependencies": self.dependencies or [],
            "status": self.status,
            "expectedOutput": self.expected_output,
            "actualOutput": self.actual_output,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }
