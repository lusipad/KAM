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
