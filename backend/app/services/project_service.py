"""
KAM v2 项目服务
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utc_now
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

        project.updated_at = utc_now()
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
            "archivedAt": utc_now().isoformat(),
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
        project.updated_at = utc_now()
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
            project.updated_at = utc_now()
        self.db.delete(resource)
        self.db.commit()
        return True

    def list_files(
        self,
        project_id: str,
        relative_path: str = "",
        include_hidden: bool = False,
        query: str | None = None,
        entry_type: str | None = None,
    ) -> dict[str, Any] | None:
        project = self.get_project(project_id)
        if not project:
            return None

        repo_root = self._resolve_repo_root(project)
        target_dir = self._resolve_repo_target(repo_root, relative_path)
        if not target_dir.exists():
            raise ValueError("指定路径不存在")
        if not target_dir.is_dir():
            raise ValueError("指定路径不是目录")

        current_path = self._relative(repo_root, target_dir)
        parent_path = None
        if target_dir != repo_root:
            parent_path = self._relative(repo_root, target_dir.parent)

        normalized_query = (query or "").strip().lower()
        normalized_type = (entry_type or "").strip().lower()
        if normalized_type not in {"dir", "file"}:
            normalized_type = ""

        all_entries: list[dict[str, Any]] = []
        for child in sorted(target_dir.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if not include_hidden and child.name.startswith('.'):
                continue
            child_path = self._relative(repo_root, child)
            try:
                stat = child.stat()
                size = stat.st_size if child.is_file() else None
            except OSError:
                size = None
            all_entries.append(
                {
                    "name": child.name,
                    "path": child_path,
                    "type": "dir" if child.is_dir() else "file",
                    "size": size,
                }
            )

        filtered_entries = [
            entry
            for entry in all_entries
            if (not normalized_type or entry["type"] == normalized_type)
            and (
                not normalized_query
                or normalized_query in entry["name"].lower()
                or normalized_query in entry["path"].lower()
            )
        ]

        return {
            "rootPath": str(repo_root),
            "currentPath": current_path,
            "parentPath": parent_path,
            "entries": filtered_entries,
            "totalEntries": len(all_entries),
            "filteredEntries": len(filtered_entries),
            "query": normalized_query,
            "entryType": normalized_type or None,
            "includeHidden": include_hidden,
        }

    def _resolve_repo_root(self, project: Project) -> Path:
        repo_path = (project.repo_path or "").strip()
        if not repo_path:
            raise ValueError("项目尚未配置 repoPath")

        repo_root = Path(repo_path).expanduser().resolve()
        if not repo_root.exists():
            raise ValueError("repoPath 不存在")
        if not repo_root.is_dir():
            raise ValueError("repoPath 不是目录")
        return repo_root

    def _resolve_repo_target(self, repo_root: Path, relative_path: str) -> Path:
        normalized = (relative_path or "").strip().lstrip("/")
        target = (repo_root / normalized).resolve()
        try:
            target.relative_to(repo_root)
        except ValueError as error:
            raise ValueError("非法路径") from error
        return target

    def _relative(self, repo_root: Path, target: Path) -> str:
        value = str(target.relative_to(repo_root)).replace("\\", "/")
        return "" if value == "." else value
