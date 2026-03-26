"""
KAM v2 Skill API。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.project_service import ProjectService
from app.services.skill_service import SkillService

router = APIRouter(prefix="/v2", tags=["v2-skills"])


class SkillCreate(BaseModel):
    scope: str = Field(default="global")
    projectId: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    promptTemplate: str = Field(..., min_length=1)
    agent: Optional[str] = None
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "user"


@router.get("/skills")
async def list_skills(
    project_id: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = SkillService(db)
    if project_id:
        project = ProjectService(db).get_project(project_id)
        if project:
            service.sync_project_skills(project_id, project.repo_path)
    return {"skills": [skill.to_dict() for skill in service.list_skills(project_id=project_id, scope=scope)]}


@router.post("/skills")
async def create_skill(data: SkillCreate, db: Session = Depends(get_db)):
    service = SkillService(db)
    skill = service.upsert_skill(data.model_dump())
    return skill.to_dict()


@router.get("/projects/{project_id}/skills")
async def list_project_skills(project_id: str, db: Session = Depends(get_db)):
    project = ProjectService(db).get_project(project_id)
    service = SkillService(db)
    if project:
        service.sync_project_skills(project_id, project.repo_path)
    return {"skills": [skill.to_dict() for skill in service.list_skills(project_id=project_id)]}
