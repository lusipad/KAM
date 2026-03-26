"""
KAM Skill 服务。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.skill import Skill


class SkillService:
    def __init__(self, db: Session):
        self.db = db

    def list_skills(self, project_id: str | None = None, scope: str | None = None) -> list[Skill]:
        query = self.db.query(Skill)
        if scope:
            query = query.filter(Skill.scope == scope)
        if project_id:
            query = query.filter(or_(Skill.project_id == project_id, Skill.scope == "global"))
        return query.order_by(Skill.scope.desc(), Skill.created_at.desc()).all()

    def find_skill(self, name: str, project_id: str | None = None) -> Skill | None:
        normalized = name.strip().lstrip("/").lower()
        if not normalized:
            return None
        if project_id:
            project_skill = (
                self.db.query(Skill)
                .filter(Skill.name == normalized, Skill.project_id == project_id)
                .order_by(Skill.created_at.desc())
                .first()
            )
            if project_skill:
                return project_skill
        return (
            self.db.query(Skill)
            .filter(Skill.name == normalized, Skill.scope == "global")
            .order_by(Skill.created_at.desc())
            .first()
        )

    def create_skill(self, data: dict[str, Any]) -> Skill:
        skill = Skill(
            scope=str(data.get("scope") or "global").strip() or "global",
            project_id=data.get("projectId") or data.get("project_id"),
            name=str(data["name"]).strip().lstrip("/").lower(),
            description=str(data.get("description") or "").strip() or None,
            prompt_template=str(data.get("promptTemplate") or data.get("prompt_template") or "").strip(),
            agent=str(data.get("agent") or "").strip() or None,
            parameters=data.get("parameters") or [],
            source=str(data.get("source") or "user").strip() or "user",
        )
        self.db.add(skill)
        self.db.commit()
        self.db.refresh(skill)
        return skill

    def upsert_skill(self, data: dict[str, Any]) -> Skill:
        scope = str(data.get("scope") or "global").strip() or "global"
        project_id = data.get("projectId") or data.get("project_id")
        name = str(data["name"]).strip().lstrip("/").lower()
        skill = (
            self.db.query(Skill)
            .filter(Skill.scope == scope, Skill.project_id == project_id, Skill.name == name)
            .first()
        )
        if skill is None:
            return self.create_skill(
                {
                    **data,
                    "scope": scope,
                    "projectId": project_id,
                    "name": name,
                }
            )

        skill.description = str(data.get("description") or skill.description or "").strip() or None
        if "promptTemplate" in data or "prompt_template" in data:
            skill.prompt_template = str(data.get("promptTemplate") or data.get("prompt_template") or "").strip()
        if "agent" in data:
            skill.agent = str(data.get("agent") or "").strip() or None
        if "parameters" in data:
            skill.parameters = data.get("parameters") or []
        if "source" in data:
            skill.source = str(data.get("source") or "user").strip() or "user"
        self.db.commit()
        self.db.refresh(skill)
        return skill

    def sync_project_skills(self, project_id: str, repo_path: str | None):
        if not repo_path:
            return []
        skills_dir = Path(repo_path) / ".claude" / "skills"
        if not skills_dir.exists():
            return []

        synced: list[Skill] = []
        for md_file in skills_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8", errors="replace")
            description = content.splitlines()[0].strip("# ").strip() if content.strip() else md_file.stem
            synced.append(
                self.upsert_skill(
                    {
                        "scope": "project",
                        "projectId": project_id,
                        "name": md_file.stem.lower(),
                        "description": description,
                        "promptTemplate": content,
                        "source": "claude-skills-dir",
                    }
                )
            )
        return synced
