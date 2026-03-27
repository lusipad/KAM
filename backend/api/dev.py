from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_db
from models import Memory, Message, Project, Run, Thread, Watcher, WatcherEvent


router = APIRouter(prefix="/dev", tags=["dev"])


class SeedDemoRequest(BaseModel):
    reset: bool = True


def _require_non_production() -> None:
    if settings.app_env == "production":
        raise HTTPException(status_code=404, detail="Not Found")


@router.post("/seed-demo")
async def seed_demo(payload: SeedDemoRequest, db: AsyncSession = Depends(get_db)):
    _require_non_production()

    if payload.reset:
        for model in (WatcherEvent, Watcher, Memory, Run, Message, Thread, Project):
            await db.execute(delete(model))
        await db.flush()

    existing = await db.get(Project, "demo-noise")
    if existing is not None:
        return {"projectId": existing.id, "threadId": "demo-login", "watcherId": "demo-ci-watcher"}

    base = datetime.now(UTC) - timedelta(minutes=18)

    project = Project(
        id="demo-noise",
        title="Noise Probe",
        repo_path="D:/Repos/KAM",
        created_at=base,
    )
    login_thread = Thread(
        id="demo-login",
        project_id=project.id,
        title="Fix login timeout",
        created_at=base + timedelta(minutes=1),
        updated_at=base + timedelta(minutes=9),
    )
    review_thread = Thread(
        id="demo-review",
        project_id=project.id,
        title="Review API contracts",
        created_at=base + timedelta(minutes=2),
        updated_at=base + timedelta(minutes=12),
    )

    db.add_all([project, login_thread, review_thread])

    db.add_all(
        [
            Message(
                id="demo-msg-user",
                thread_id=login_thread.id,
                role="user",
                content="Login timeout after 30s. Fix this.",
                created_at=base + timedelta(minutes=3),
            ),
            Message(
                id="demo-msg-assistant",
                thread_id=login_thread.id,
                role="assistant",
                content="I can see this is happening in the auth flow. I started a background fix run.",
                created_at=base + timedelta(minutes=4),
            ),
            Message(
                id="demo-msg-review",
                thread_id=review_thread.id,
                role="assistant",
                content="I checked the CI regression and the API contract mismatch is still the likely root cause.",
                created_at=base + timedelta(minutes=11),
            ),
        ]
    )

    db.add_all(
        [
            Run(
                id="demo-run-pass",
                thread_id=login_thread.id,
                agent="codex",
                status="passed",
                task="Fix login timeout in the auth flow",
                result_summary="Updated the token refresh path, removed the duplicate timeout branch, and checks passed.",
                changed_files=["src/auth.ts", "src/interceptor.ts", "src/auth.test.ts"],
                check_passed=True,
                duration_ms=1300,
                raw_output="Checks passed.\nUpdated auth.ts",
                created_at=base + timedelta(minutes=5),
            ),
            Run(
                id="demo-run-fail",
                thread_id=review_thread.id,
                agent="codex",
                status="failed",
                task="Review API contracts for the new memory endpoints",
                result_summary="Test auth.test.ts:42 failed because the response shape still returns the old payload.",
                changed_files=["backend/api/memory_api.py"],
                check_passed=False,
                duration_ms=4200,
                raw_output="auth.test.ts:42 expected 200 but received 204",
                created_at=base + timedelta(minutes=10),
            ),
        ]
    )

    db.add_all(
        [
            Memory(
                id="demo-mem-pref",
                project_id=project.id,
                scope="project",
                category="preference",
                content="Testing: always run backend tests before marking done",
                rationale="This repo treats test-green as the exit gate.",
                created_at=base + timedelta(minutes=6),
                last_accessed_at=base + timedelta(minutes=6),
            ),
            Memory(
                id="demo-mem-decision",
                project_id=project.id,
                scope="project",
                category="decision",
                content="Architecture: V3 drops the old /api/v2 compatibility layer",
                rationale="The repo now optimizes for a single clean path.",
                created_at=base + timedelta(minutes=7),
                last_accessed_at=base + timedelta(minutes=7),
            ),
            Memory(
                id="demo-mem-learning",
                project_id=project.id,
                scope="project",
                category="learning",
                content="Watcher alerts should land in Home before they interrupt a thread",
                rationale="That keeps background noise out of the conversation flow.",
                created_at=base + timedelta(minutes=8),
                last_accessed_at=base + timedelta(minutes=8),
            ),
        ]
    )

    watcher = Watcher(
        id="demo-ci-watcher",
        project_id=project.id,
        name="CI monitor",
        source_type="ci_pipeline",
        config={"repo": "lusipad/KAM", "provider": "github_actions", "branch": "main"},
        schedule_type="interval",
        schedule_value="15m",
        status="active",
        auto_action_level=1,
        last_run_at=base + timedelta(minutes=13),
        last_state={"items": []},
        created_at=base + timedelta(minutes=9),
    )
    db.add(watcher)
    db.add(
        WatcherEvent(
            id="demo-ci-event",
            watcher_id=watcher.id,
            thread_id=review_thread.id,
            event_type="ci_failed",
            title="CI failed on main",
            summary="Build #892 failed at test stage. AI analysis points to the memory API response shape.",
            raw_data={"changes": {"created": [{"id": 892, "head_branch": "main"}]}},
            actions=[
                {"label": "View thread", "kind": "create_run", "params": {"agent": "codex", "task": "Inspect the CI failure and propose a fix."}},
                {"label": "Auto-fix", "kind": "create_run", "params": {"agent": "codex", "task": "Fix the CI failure in the memory API."}},
            ],
            status="pending",
            created_at=base + timedelta(minutes=14),
        )
    )

    await db.commit()
    return {"projectId": project.id, "threadId": login_thread.id, "watcherId": watcher.id}
