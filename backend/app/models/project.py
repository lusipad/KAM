"""
KAM v2 项目模型
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class Project(Base):
    __tablename__ = "projects"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    title = Column(String(200), nullable=False)
    status = Column(String(20), default="active")
    repo_path = Column(String(1000), nullable=True)
    description = Column(Text, default="")
    check_commands = Column(JSON, default=list)
    settings_ = Column("settings", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    resources = relationship(
        "ProjectResource",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectResource.created_at.desc()",
    )
    threads = relationship(
        "Thread",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Thread.updated_at.desc()",
    )
    decisions = relationship(
        "DecisionLog",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="DecisionLog.created_at.desc()",
    )
    learnings = relationship(
        "ProjectLearning",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectLearning.created_at.desc()",
    )
    skills = relationship(
        "Skill",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Skill.created_at.desc()",
    )

    __table_args__ = (
        Index("idx_projects_status", "status"),
        Index("idx_projects_updated", "updated_at"),
    )

    def to_dict(self, include_relations: bool = False, include_threads: bool = False):
        data = {
            "id": str(self.id),
            "title": self.title,
            "status": self.status,
            "repoPath": self.repo_path,
            "description": self.description,
            "checkCommands": self.check_commands or [],
            "settings": self.settings_ or {},
            "resourceCount": len(self.resources or []),
            "threadCount": len(self.threads or []),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_relations:
            resources = [resource.to_dict() for resource in self.resources] if self.resources else []
            data["resources"] = resources
            data["pinnedResources"] = [resource for resource in resources if resource["pinned"]]
            if include_threads:
                data["threads"] = [thread.to_dict(include_relations=False) for thread in self.threads] if self.threads else []
        return data


class ProjectResource(Base):
    __tablename__ = "project_resources"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    project_id = Column(uuid_type(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    resource_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=True)
    uri = Column(Text, nullable=False)
    pinned = Column(Boolean, default=False)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    project = relationship("Project", back_populates="resources")

    __table_args__ = (
        Index("idx_project_resources_project", "project_id"),
        Index("idx_project_resources_pinned", "pinned"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "projectId": str(self.project_id),
            "type": self.resource_type,
            "title": self.title,
            "uri": self.uri,
            "pinned": bool(self.pinned),
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
