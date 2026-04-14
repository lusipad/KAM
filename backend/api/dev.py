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
        title="处理 GitHub issue：首页要讲清持续推进链路",
        description="把 GitHub issue 接入 KAM 任务池，并把首页改成用户一眼就能看懂外部输入、执行留痕和继续推进链路。",
        repo_path="D:/Repos/KAM",
        status="in_progress",
        priority="high",
        labels=["dogfood", "harness"],
        metadata_={
            "recommendedAgent": "codex",
            "recommendedPrompt": "处理 issue 诉求，先把首页差异点和默认演示链路讲清，再补 smoke 验证。",
            "sourceKind": "github_issue",
            "sourceDedupKey": "github_issue:lusipad/KAM:4519",
            "sourceRepo": "lusipad/KAM",
            "sourceIssueNumber": 4519,
            "sourceIssueTitle": "首页需要一眼讲清 KAM 的持续推进链路",
            "sourceIssueBody": "让新用户打开后马上明白，KAM 不是另一个聊天式 coding assistant，而是 AI 工程控制面。",
            "sourceIssueComments": [
                {
                    "id": 7001,
                    "user": "lus",
                    "body": "把差异点证据和默认 demo flow 直接做进首页，不要只放在 README 里。",
                    "html_url": "https://github.com/lusipad/KAM/issues/4519#issuecomment-7001",
                }
            ],
        },
        created_at=base,
        updated_at=base + timedelta(minutes=9),
    )
    db.add(task)

    db.add_all(
        [
            TaskRef(
                id="task-ref-issue",
                task_id=task.id,
                kind="url",
                label="GitHub Issue",
                value="https://github.com/lusipad/KAM/issues/4519",
                created_at=base + timedelta(minutes=1),
            ),
            TaskRef(
                id="task-ref-frontdoor",
                task_id=task.id,
                kind="file",
                label="Front Door Panel",
                value="app/src/features/operator/FrontDoorPanel.tsx",
                created_at=base + timedelta(minutes=2),
            ),
            ContextSnapshot(
                id="task-snapshot-1",
                task_id=task.id,
                summary="处理 GitHub issue：首页要讲清持续推进链路 · 2 refs",
                content=(
                    "## Task\n"
                    "标题：处理 GitHub issue：首页要讲清持续推进链路\n\n"
                    "## Source\n"
                    "- GitHub Issue: lusipad/KAM#4519\n"
                    "- 核心诉求：让首页直接讲清差异点证据和默认 demo flow\n\n"
                    "## Refs\n"
                    "- [url] GitHub Issue: https://github.com/lusipad/KAM/issues/4519\n"
                    "- [file] Front Door Panel: app/src/features/operator/FrontDoorPanel.tsx"
                ),
                focus="先把首页差异点和默认演示链路讲清，再接 smoke。",
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
                task="先把 GitHub issue 收成任务对象并补首页演示上下文",
                result_summary="GitHub issue 已入任务池，首页目标和默认演示上下文已经收口。",
                changed_files=["backend/scripts/github_issue_monitor.py", "backend/services/task_planner.py"],
                check_passed=True,
                duration_ms=1400,
                raw_output="Issue 已入池。\n任务和推荐 prompt 已补齐。",
                created_at=base + timedelta(minutes=4),
            ),
            TaskRun(
                id="task-run-2",
                task_id=task.id,
                agent="codex",
                status="passed",
                task="把首页改成一眼看懂持续推进链路",
                result_summary="首页已经补出差异点证据区和默认演示链路，控制面继续保留人工接管入口。",
                changed_files=["app/src/features/operator/FrontDoorPanel.tsx", "app/src/index.css", "app/e2e/harness-smoke.spec.ts"],
                check_passed=True,
                duration_ms=2200,
                raw_output="首页差异点区已接上。\n默认演示链路已更新。",
                created_at=base + timedelta(minutes=8),
            ),
        ]
    )

    db.add_all(
        [
            TaskRunArtifact(
                id="artifact-1",
                task_run_id="task-run-1",
                type="github_issue_context",
                content="来源：lusipad/KAM#4519\n诉求：首页需要直接讲清 KAM 的持续推进链路。",
                created_at=base + timedelta(minutes=4),
            ),
            TaskRunArtifact(
                id="artifact-2",
                task_run_id="task-run-1",
                type="changed_files",
                content='["backend/scripts/github_issue_monitor.py","backend/services/task_planner.py"]',
                created_at=base + timedelta(minutes=4),
            ),
            TaskRunArtifact(
                id="artifact-3",
                task_run_id="task-run-2",
                type="summary",
                content="首页已经补出差异点证据区和默认演示链路，控制面继续保留人工接管入口。",
                created_at=base + timedelta(minutes=8),
            ),
            TaskRunArtifact(
                id="artifact-4",
                task_run_id="task-run-2",
                type="stdout",
                content="首页差异点区已接上。\n默认演示链路已更新。",
                created_at=base + timedelta(minutes=8),
            ),
        ]
    )

    db.add(
        ReviewCompare(
            id="task-compare-1",
            task_id=task.id,
            title="首页持续推进链路 · compare",
            run_ids=["task-run-1", "task-run-2"],
            summary="对比 2 个 run：外部 GitHub issue 已收进任务池，首页也把差异点和继续推进链路讲清了。",
            created_at=base + timedelta(minutes=9),
        )
    )

    await db.commit()
    return {"taskId": task.id, "runId": "task-run-2", "compareId": "task-compare-1"}
