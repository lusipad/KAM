"""
KAM v2 项目服务
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.project import Project, ProjectResource


class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def list_projects(self, status: str | None = None) -> list[Project]:
        query = self.db.query(Project)
        if status:
            query = query.filter(Project.status == status)
        return query.order_by(Project.updated_at.desc()).all()

    def create_project(self, data: dict[str, Any]) -> Project:
        project = Project(
            title=data["title"],
            status=data.get("status", "active"),
            repo_path=data.get("repoPath") or data.get("repo_path"),
            description=data.get("description", ""),
            check_commands=data.get("checkCommands") or data.get("check_commands") or [],
            settings_=data.get("settings") or {},
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_project(self, project_id: str) -> Project | None:
        return self.db.query(Project).filter(Project.id == project_id).first()

    def update_project(self, project_id: str, data: dict[str, Any]) -> Project | None:
        project = self.get_project(project_id)
        if not project:
            return None

        if "title" in data:
            project.title = data["title"]
        if "status" in data:
            project.status = data["status"]
        if "repoPath" in data or "repo_path" in data:
            project.repo_path = data.get("repoPath") or data.get("repo_path")
        if "description" in data:
            project.description = data["description"] or ""
        if "checkCommands" in data or "check_commands" in data:
            project.check_commands = data.get("checkCommands") or data.get("check_commands") or []
        if "settings" in data:
            project.settings_ = {**(project.settings_ or {}), **(data.get("settings") or {})}

        project.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(project)
        return project

    def archive_project(self, project_id: str) -> Project | None:
        project = self.get_project(project_id)
        if not project:
            return None

        project.status = "done"
        project.settings_ = {
            **(project.settings_ or {}),
            "archivedAt": datetime.utcnow().isoformat(),
        }
        self.db.commit()
        self.db.refresh(project)
        return project

    def list_resources(self, project_id: str, pinned: bool | None = None) -> list[ProjectResource]:
        query = self.db.query(ProjectResource).filter(ProjectResource.project_id == project_id)
        if pinned is not None:
            query = query.filter(ProjectResource.pinned == pinned)
        return query.order_by(ProjectResource.created_at.desc()).all()

    def add_resource(self, project_id: str, data: dict[str, Any]) -> ProjectResource | None:
        project = self.get_project(project_id)
        if not project:
            return None

        resource = ProjectResource(
            project_id=project.id,
            resource_type=data["type"],
            title=data.get("title"),
            uri=data["uri"],
            pinned=bool(data.get("pinned", False)),
            metadata_=data.get("metadata") or {},
        )
        self.db.add(resource)
        project.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(resource)
        return resource

    def delete_resource(self, project_id: str, resource_id: str) -> bool:
        resource = (
            self.db.query(ProjectResource)
            .filter(ProjectResource.id == resource_id, ProjectResource.project_id == project_id)
            .first()
        )
        if not resource:
            return False

        project = self.get_project(project_id)
        if project:
            project.updated_at = datetime.utcnow()
        self.db.delete(resource)
        self.db.commit()
        return True
