"""
KAM Skill 模型。
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class Skill(Base):
    __tablename__ = "skills"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    scope = Column(String(20), nullable=False)
    project_id = Column(uuid_type(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=False)
    agent = Column(String(50), nullable=True)
    parameters = Column(JSON, default=list)
    source = Column(String(50), default="user")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    project = relationship("Project", back_populates="skills")

    __table_args__ = (
        Index("idx_skills_scope", "scope"),
        Index("idx_skills_project", "project_id"),
        UniqueConstraint("scope", "project_id", "name", name="uq_skills_scope_project_name"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "scope": self.scope,
            "projectId": str(self.project_id) if self.project_id else None,
            "name": self.name,
            "description": self.description,
            "promptTemplate": self.prompt_template,
            "agent": self.agent,
            "parameters": self.parameters or [],
            "source": self.source,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
