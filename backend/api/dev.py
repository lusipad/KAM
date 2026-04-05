from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_db
from models import ContextSnapshot, ReviewCompare, Task, TaskRef, TaskRun, TaskRunArtifact
from services.run_engine import wait_for_background_runs
from services.task_autodrive import reset_autodrive_runtime_state


router = APIRouter(prefix="/dev", tags=["dev"])


class SeedHarnessRequest(BaseModel):
    reset: bool = True


RESET_MODELS = (
    ReviewCompare,
    TaskRunArtifact,
    TaskRun,
    ContextSnapshot,
    TaskRef,
    Task,
)


def _require_non_production() -> None:
    if settings.app_env == "production":
        raise HTTPException(status_code=404, detail="未找到页面")


async def _reset_dev_data(db: AsyncSession) -> None:
    for model in RESET_MODELS:
        await db.execute(delete(model))
    await db.flush()


@router.post("/seed-harness")
async def seed_harness(payload: SeedHarnessRequest, db: AsyncSession = Depends(get_db)):
    _require_non_production()

    if payload.reset:
        reset_autodrive_runtime_state(clear_persistence=True)
        await wait_for_background_runs()
        await _reset_dev_data(db)

    existing = await db.get(Task, "task-harness-cutover")
    if existing is not None:
        return {"taskId": existing.id, "runId": "task-run-2", "compareId": "task-compare-1"}

    base = datetime.now(UTC) - timedelta(minutes=12)

    task = Task(
        id="task-harness-cutover",
        title="切到 task-first harness",
        description="把当前默认入口从 V3 workspace 切成 task-first harness，并保持 dogfood 可用。",
        repo_path="D:/Repos/KAM",
        status="in_progress",
        priority="high",
        labels=["dogfood", "harness"],
        created_at=base,
        updated_at=base + timedelta(minutes=9),
    )
    db.add(task)

    db.add_all(
        [
            TaskRef(
                id="task-ref-prd",
                task_id=task.id,
                kind="file",
                label="PRD",
                value="docs/product/ai_work_assistant_prd.md",
                created_at=base + timedelta(minutes=1),
            ),
            TaskRef(
                id="task-ref-app",
                task_id=task.id,
                kind="file",
                label="App Entry",
                value="app/src/App.tsx",
                created_at=base + timedelta(minutes=2),
            ),
            ContextSnapshot(
                id="task-snapshot-1",
                task_id=task.id,
                summary="切到 task-first harness · 2 refs",
                content="## Task\n标题：切到 task-first harness\n\n## Refs\n- [file] PRD: docs/product/ai_work_assistant_prd.md\n- [file] App Entry: app/src/App.tsx",
                focus="先切前端主入口，再接 smoke。",
                created_at=base + timedelta(minutes=3),
            ),
        ]
    )

    db.add_all(
        [
            TaskRun(
                id="task-run-1",
                task_id=task.id,
                agent="codex",
                status="passed",
                task="先建立 Task 和 Snapshot API",
                result_summary="已接上 Task、Ref、Snapshot 基础接口。",
                changed_files=["backend/api/tasks.py", "backend/services/task_context.py"],
                check_passed=True,
                duration_ms=1400,
                raw_output="Task API 已接通。\nSnapshot 可生成。",
                created_at=base + timedelta(minutes=4),
            ),
            TaskRun(
                id="task-run-2",
                task_id=task.id,
                agent="codex",
                status="passed",
                task="把前端默认入口切到 task-first harness",
                result_summary="默认入口已切到 task-first workbench，旧 V3 workspace 退出主路径。",
                changed_files=["app/src/App.tsx", "app/src/features/tasks/TaskWorkbench.tsx", "app/e2e/harness-smoke.spec.ts"],
                check_passed=True,
                duration_ms=2200,
                raw_output="前端主入口已切换。\nSmoke 已更新。",
                created_at=base + timedelta(minutes=8),
            ),
        ]
    )

    db.add_all(
        [
            TaskRunArtifact(
                id="artifact-1",
                task_run_id="task-run-1",
                type="summary",
                content="已接上 Task、Ref、Snapshot 基础接口。",
                created_at=base + timedelta(minutes=4),
            ),
            TaskRunArtifact(
                id="artifact-2",
                task_run_id="task-run-1",
                type="changed_files",
                content='["backend/api/tasks.py","backend/services/task_context.py"]',
                created_at=base + timedelta(minutes=4),
            ),
            TaskRunArtifact(
                id="artifact-3",
                task_run_id="task-run-2",
                type="summary",
                content="默认入口已切到 task-first workbench，旧 V3 workspace 退出主路径。",
                created_at=base + timedelta(minutes=8),
            ),
            TaskRunArtifact(
                id="artifact-4",
                task_run_id="task-run-2",
                type="stdout",
                content="前端主入口已切换。\nSmoke 已更新。",
                created_at=base + timedelta(minutes=8),
            ),
        ]
    )

    db.add(
        ReviewCompare(
            id="task-compare-1",
            task_id=task.id,
            title="切到 task-first harness · compare",
            run_ids=["task-run-1", "task-run-2"],
            summary="对比 2 个 run：后端骨架已经接上，前端主入口切换也已完成。",
            created_at=base + timedelta(minutes=9),
        )
    )

    await db.commit()
    return {"taskId": task.id, "runId": "task-run-2", "compareId": "task-compare-1"}
