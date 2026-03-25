"""
KAM v2 项目 API
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.project_service import ProjectService

router = APIRouter(prefix="/v2", tags=["v2-projects"])


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    status: str = "active"
    repoPath: Optional[str] = None
    description: str = ""
    checkCommands: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[str] = None
    repoPath: Optional[str] = None
    description: Optional[str] = None
    checkCommands: Optional[list[str]] = None
    settings: Optional[dict[str, Any]] = None


class ProjectResourceCreate(BaseModel):
    type: str = Field(..., min_length=1, max_length=50)
    title: Optional[str] = Field(default=None, max_length=200)
    uri: str = Field(..., min_length=1)
    pinned: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/projects")
async def list_projects(status: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    service = ProjectService(db)
    return {"projects": [project.to_dict() for project in service.list_projects(status=status)]}


@router.post("/projects")
async def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    service = ProjectService(db)
    return service.create_project(data.model_dump()).to_dict()


@router.get("/projects/{project_id}")
async def get_project(project_id: str, db: Session = Depends(get_db)):
    service = ProjectService(db)
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project.to_dict(include_relations=True, include_threads=True)


@router.put("/projects/{project_id}")
async def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    service = ProjectService(db)
    project = service.update_project(project_id, data.model_dump(exclude_unset=True))
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project.to_dict(include_relations=True, include_threads=True)


@router.post("/projects/{project_id}/archive")
async def archive_project(project_id: str, db: Session = Depends(get_db)):
    service = ProjectService(db)
    project = service.archive_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project.to_dict()


@router.get("/projects/{project_id}/resources")
async def list_resources(
    project_id: str,
    pinned: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    return {"resources": [resource.to_dict() for resource in service.list_resources(project_id, pinned=pinned)]}


@router.post("/projects/{project_id}/resources")
async def add_resource(project_id: str, data: ProjectResourceCreate, db: Session = Depends(get_db)):
    service = ProjectService(db)
    resource = service.add_resource(project_id, data.model_dump())
    if not resource:
        raise HTTPException(status_code=404, detail="项目不存在")
    return resource.to_dict()


@router.delete("/projects/{project_id}/resources/{resource_id}")
async def delete_resource(project_id: str, resource_id: str, db: Session = Depends(get_db)):
    service = ProjectService(db)
    deleted = service.delete_resource(project_id, resource_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="资源不存在")
    return {"message": "删除成功"}


@router.get("/projects/{project_id}/files")
async def list_project_files(
    project_id: str,
    path: str = Query(default=""),
    include_hidden: bool = Query(default=False),
    query: str = Query(default=""),
    entry_type: str = Query(default=""),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    try:
        tree = service.list_files(
            project_id,
            relative_path=path,
            include_hidden=include_hidden,
            query=query,
            entry_type=entry_type,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not tree:
        raise HTTPException(status_code=404, detail="项目不存在")
    return tree
