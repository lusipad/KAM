from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_db
from models import (
    ContextSnapshot,
    Memory,
    Message,
    Project,
    ReviewCompare,
    Run,
    RunArtifact,
    Task,
    TaskRef,
    Thread,
    Watcher,
    WatcherEvent,
)


router = APIRouter(prefix="/dev", tags=["dev"])


class SeedDemoRequest(BaseModel):
    reset: bool = True


RESET_MODELS = (
    ReviewCompare,
    RunArtifact,
    ContextSnapshot,
    TaskRef,
    Task,
    WatcherEvent,
    Watcher,
    Memory,
    Run,
    Message,
    Thread,
    Project,
)


def _require_non_production() -> None:
    if settings.app_env == "production":
        raise HTTPException(status_code=404, detail="未找到页面")


async def _reset_dev_data(db: AsyncSession) -> None:
    for model in RESET_MODELS:
        await db.execute(delete(model))
    await db.flush()


@router.post("/seed-demo")
async def seed_demo(payload: SeedDemoRequest, db: AsyncSession = Depends(get_db)):
    _require_non_production()

    if payload.reset:
        await _reset_dev_data(db)

    existing = await db.get(Project, "demo-noise")
    if existing is not None:
        return {"projectId": existing.id, "threadId": "demo-login", "watcherId": "demo-ci-watcher"}

    base = datetime.now(UTC) - timedelta(minutes=18)

    project = Project(
        id="demo-noise",
        title="信号探针",
        repo_path="D:/Repos/KAM",
        created_at=base,
    )
    login_thread = Thread(
        id="demo-login",
        project_id=project.id,
        title="修复登录超时",
        created_at=base + timedelta(minutes=1),
        updated_at=base + timedelta(minutes=9),
    )
    review_thread = Thread(
        id="demo-review",
        project_id=project.id,
        title="核对 API 契约",
        created_at=base + timedelta(minutes=2),
        updated_at=base + timedelta(minutes=12),
    )
    running_thread = Thread(
        id="demo-running",
        project_id=project.id,
        title="补全 watcher 启动流程",
        created_at=base + timedelta(minutes=2, seconds=30),
        updated_at=base + timedelta(minutes=15),
    )
    shipped_thread = Thread(
        id="demo-shipped",
        project_id=project.id,
        title="整理发布说明",
        created_at=base + timedelta(minutes=1, seconds=30),
        updated_at=base + timedelta(minutes=8),
    )

    db.add_all([project, login_thread, review_thread, running_thread, shipped_thread])

    db.add_all(
        [
            Message(
                id="demo-msg-user",
                thread_id=login_thread.id,
                role="user",
                content="登录 30 秒后超时，修一下。",
                created_at=base + timedelta(minutes=3),
            ),
            Message(
                id="demo-msg-assistant",
                thread_id=login_thread.id,
                role="assistant",
                content="我看到问题出在鉴权链路，已经启动后台修复任务。",
                created_at=base + timedelta(minutes=4),
            ),
            Message(
                id="demo-msg-review",
                thread_id=review_thread.id,
                role="assistant",
                content="我检查了 CI 回归，API 契约不匹配仍然是最可能的根因。",
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
                task="修复鉴权流程中的登录超时",
                result_summary="已更新 token 刷新路径，移除重复超时分支，检查通过。",
                changed_files=["src/auth.ts", "src/interceptor.ts", "src/auth.test.ts"],
                check_passed=True,
                duration_ms=1300,
                raw_output="检查通过。\n已更新 auth.ts",
                created_at=base + timedelta(minutes=5),
            ),
            Run(
                id="demo-run-fail",
                thread_id=review_thread.id,
                agent="codex",
                status="failed",
                task="检查新的记忆接口 API 契约",
                result_summary="auth.test.ts:42 失败，原因是响应结构仍然返回旧 payload。",
                changed_files=["backend/api/memory_api.py"],
                check_passed=False,
                duration_ms=4200,
                raw_output="auth.test.ts:42 预期 200，实际 204",
                created_at=base + timedelta(minutes=10),
            ),
            Run(
                id="demo-run-running",
                thread_id=running_thread.id,
                agent="codex",
                status="running",
                task="补全 watcher 启动与恢复链路",
                result_summary=None,
                changed_files=["app/src/features/thread/ThreadView.tsx", "backend/api/watchers.py"],
                check_passed=None,
                duration_ms=None,
                raw_output="正在串起启用、暂停、恢复流程，并补 smoke 验证。",
                created_at=base + timedelta(minutes=15),
            ),
            Run(
                id="demo-run-adopted",
                thread_id=shipped_thread.id,
                agent="codex",
                status="passed",
                task="整理发布说明并同步本地验证步骤",
                result_summary="已整理发布说明并同步验证步骤。",
                changed_files=["README.md", "docs/README.md"],
                check_passed=True,
                duration_ms=1800,
                adopted_at=base + timedelta(minutes=8),
                raw_output="文档已更新。\n本地验证步骤已同步。",
                created_at=base + timedelta(minutes=7),
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
                content="测试要求：标记完成前必须先跑后端测试",
                rationale="这个仓库把测试全绿当作退出门槛。",
                created_at=base + timedelta(minutes=6),
                last_accessed_at=base + timedelta(minutes=6),
            ),
            Memory(
                id="demo-mem-decision",
                project_id=project.id,
                scope="project",
                category="decision",
                content="架构决策：V3 去掉旧的 /api/v2 兼容层",
                rationale="仓库现在只优化一条干净路径。",
                created_at=base + timedelta(minutes=7),
                last_accessed_at=base + timedelta(minutes=7),
            ),
            Memory(
                id="demo-mem-learning",
                project_id=project.id,
                scope="project",
                category="learning",
                content="监控提醒要先落到首页，再决定是否打断线程",
                rationale="这样能把后台噪音挡在对话流之外。",
                created_at=base + timedelta(minutes=8),
                last_accessed_at=base + timedelta(minutes=8),
            ),
        ]
    )

    watcher = Watcher(
        id="demo-ci-watcher",
        project_id=project.id,
        name="CI 监控",
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
            title="main 分支 CI 失败",
            summary="构建 #892 在测试阶段失败。AI 分析指向 memory API 的响应结构。",
            raw_data={"changes": {"created": [{"id": 892, "head_branch": "main"}]}},
            actions=[
                {"label": "查看线程", "kind": "create_run", "params": {"agent": "codex", "task": "检查这次 CI 失败并给出修复方案。"}},
                {"label": "自动修复", "kind": "create_run", "params": {"agent": "codex", "task": "修复 memory API 中导致 CI 失败的问题。"}},
            ],
            status="pending",
            created_at=base + timedelta(minutes=14),
        )
    )

    await db.commit()
    return {"projectId": project.id, "threadId": login_thread.id, "watcherId": watcher.id}


@router.post("/seed-harness")
async def seed_harness(payload: SeedDemoRequest, db: AsyncSession = Depends(get_db)):
    _require_non_production()

    if payload.reset:
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
        metadata_={"bridgeProjectId": "task-bridge-project", "bridgeThreadId": "task-bridge-thread"},
        created_at=base,
        updated_at=base + timedelta(minutes=9),
    )
    project = Project(
        id="task-bridge-project",
        title="__task__ 切到 task-first harness",
        repo_path="D:/Repos/KAM",
        created_at=base,
    )
    thread = Thread(
        id="task-bridge-thread",
        project_id=project.id,
        title=task.title,
        created_at=base,
        updated_at=base + timedelta(minutes=9),
    )
    db.add_all([task, project, thread])

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
            Run(
                id="task-run-1",
                thread_id=thread.id,
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
            Run(
                id="task-run-2",
                thread_id=thread.id,
                agent="claude-code",
                status="passed",
                task="把前端默认入口切到 task-first harness",
                result_summary="默认入口已切到 task-first workbench，旧 V3 workspace 退出主路径。",
                changed_files=["app/src/App.tsx", "app/src/features/tasks/TaskWorkbench.tsx", "app/e2e/v3-smoke.spec.ts"],
                check_passed=True,
                duration_ms=2200,
                raw_output="前端主入口已切换。\nSmoke 已更新。",
                created_at=base + timedelta(minutes=8),
            ),
        ]
    )

    db.add_all(
        [
            RunArtifact(
                id="artifact-1",
                run_id="task-run-1",
                type="summary",
                content="已接上 Task、Ref、Snapshot 基础接口。",
                created_at=base + timedelta(minutes=4),
            ),
            RunArtifact(
                id="artifact-2",
                run_id="task-run-1",
                type="changed_files",
                content='["backend/api/tasks.py","backend/services/task_context.py"]',
                created_at=base + timedelta(minutes=4),
            ),
            RunArtifact(
                id="artifact-3",
                run_id="task-run-2",
                type="summary",
                content="默认入口已切到 task-first workbench，旧 V3 workspace 退出主路径。",
                created_at=base + timedelta(minutes=8),
            ),
            RunArtifact(
                id="artifact-4",
                run_id="task-run-2",
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
