from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.github_issue_monitors import (
    list_issue_monitors,
    remove_issue_monitor,
    run_issue_monitor_once,
    upsert_issue_monitor,
)


router = APIRouter(prefix="/issue-monitors", tags=["issue-monitors"])


class IssueMonitorUpsertRequest(BaseModel):
    repo: str = Field(min_length=3, max_length=200)
    repoPath: str | None = Field(default=None, max_length=500)
    runNow: bool = True


@router.get("")
async def get_issue_monitors():
    return {"monitors": list_issue_monitors()}


@router.post("")
async def create_or_update_issue_monitor(payload: IssueMonitorUpsertRequest, request: Request):
    try:
        monitor = await upsert_issue_monitor(
            payload.repo,
            payload.repoPath,
            app=request.app,
            run_now=payload.runNow,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return monitor


@router.post("/{owner}/{name}/run-once")
async def run_issue_monitor(owner: str, name: str, request: Request):
    repo = f"{owner}/{name}"
    try:
        return await run_issue_monitor_once(repo, request.app)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{owner}/{name}")
async def delete_issue_monitor(owner: str, name: str):
    repo = f"{owner}/{name}"
    try:
        removed = await remove_issue_monitor(repo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="issue monitor 未注册。")
    return {"ok": True, "repo": repo}
