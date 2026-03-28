from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import get_db
from models import Project, Thread
from services.title_generation import TitleGenerationService


router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    repoPath: str | None = Field(default=None, max_length=500)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    repoPath: str | None = Field(default=None, max_length=500)


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    externalRef: dict | None = None


class BootstrapConversation(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    repoPath: str | None = Field(default=None, max_length=500)


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return {"projects": [project.to_dict() for project in result.scalars()]}


@router.post("")
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(title=payload.title.strip(), repo_path=payload.repoPath.strip() if payload.repoPath else None)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project.to_dict()


@router.post("/bootstrap")
async def bootstrap_conversation(payload: BootstrapConversation, db: AsyncSession = Depends(get_db)):
    project_title, thread_title = await TitleGenerationService().generate(
        payload.prompt,
        repo_path=payload.repoPath.strip() if payload.repoPath else None,
    )
    project = Project(title=project_title, repo_path=payload.repoPath.strip() if payload.repoPath else None)
    db.add(project)
    await db.flush()
    thread = Thread(project_id=project.id, title=thread_title)
    db.add(thread)
    await db.commit()
    await db.refresh(project)
    await db.refresh(thread)
    return {"project": project.to_dict(), "thread": thread.to_summary_dict()}


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Project).where(Project.id == project_id).options(selectinload(Project.threads))
    result = await db.execute(stmt)
    project = result.scalars().first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {**project.to_dict(), "threads": [thread.to_summary_dict() for thread in project.threads]}


@router.put("/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.title is not None:
        project.title = payload.title.strip()
    if payload.repoPath is not None:
        project.repo_path = payload.repoPath.strip() or None
    await db.commit()
    await db.refresh(project)
    return project.to_dict()


@router.post("/{project_id}/threads")
async def create_thread(project_id: str, payload: ThreadCreate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    thread = Thread(
        project_id=project_id,
        title=(payload.title or "新对话").strip(),
        external_ref=payload.externalRef,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread.to_summary_dict()
