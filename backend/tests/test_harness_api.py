from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text


TMP_ROOT = Path(tempfile.mkdtemp(prefix="kam-harness-tests-"))
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP_ROOT / 'kam-harness.db').as_posix()}"
os.environ["STORAGE_PATH"] = str(TMP_ROOT)
os.environ["RUN_ROOT"] = str(TMP_ROOT / "runs")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["APP_ENV"] = "test"

import config  # noqa: E402
from db import async_session, engine  # noqa: E402
from main import app  # noqa: E402
from models import ContextSnapshot, Task, TaskRun  # noqa: E402
from services.run_engine import RunEngine, wait_for_background_runs  # noqa: E402
from services.source_tasks import source_task_guard  # noqa: E402
from services.task_autodrive import (  # noqa: E402
    GLOBAL_AUTO_DRIVE_LEASE_FILENAME,
    GLOBAL_AUTO_DRIVE_STATE_FILENAME,
    GlobalAutoDriveService,
    _GLOBAL_STATE,
    reset_autodrive_runtime_state,
)


class HarnessApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        reset_autodrive_runtime_state(clear_persistence=True)
        asyncio.run(self._truncate_tables())

    def tearDown(self):
        asyncio.run(wait_for_background_runs())
        reset_autodrive_runtime_state(clear_persistence=True)
        self.client.__exit__(None, None, None)
        asyncio.run(engine.dispose())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_task_ref_snapshot_run_artifacts_and_compare_flow(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "切换到 harness 主线",
                "description": "把当前默认入口切到 task-first harness。",
                "repoPath": "D:/Repos/KAM",
                "labels": ["harness", "dogfood"],
            },
        ).json()

        ref = self.client.post(
            f"/api/tasks/{task['id']}/refs",
            json={"kind": "file", "label": "PRD", "value": "docs/product/ai_work_assistant_prd.md"},
        ).json()
        self.assertEqual(ref["kind"], "file")

        snapshot = self.client.post(
            f"/api/tasks/{task['id']}/context/resolve",
            json={"focus": "先按 task-first harness 拆骨架。"},
        ).json()
        self.assertIn("## Task", snapshot["content"])
        self.assertIn("## Refs", snapshot["content"])

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：task-first harness"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            run_one = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "codex", "task": "先建立 Task 和 Snapshot API"},
            ).json()
            run_two = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "claude-code", "task": "补 Compare 和 Artifacts API"},
            ).json()
            retried = self.client.post(f"/api/runs/{run_one['id']}/retry").json()

        self.assertEqual(run_one["status"], "passed")
        self.assertEqual(run_two["status"], "passed")
        self.assertEqual(retried["status"], "passed")
        self.assertEqual(run_one["taskId"], task["id"])
        self.assertIsNone(run_one["threadId"])

        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(len(detail["refs"]), 1)
        self.assertEqual(len(detail["snapshots"]), 1)
        self.assertEqual(len(detail["runs"]), 3)
        self.assertTrue(all(item["threadId"] is None for item in detail["runs"]))

        artifacts = self.client.get(f"/api/runs/{run_one['id']}/artifacts").json()["artifacts"]
        artifact_types = {artifact["type"] for artifact in artifacts}
        self.assertTrue({"task_snapshot", "context_snapshot", "task", "stdout", "summary"}.issubset(artifact_types))

        retried_artifacts = self.client.get(f"/api/runs/{retried['id']}/artifacts").json()["artifacts"]
        retried_types = {artifact["type"] for artifact in retried_artifacts}
        self.assertTrue({"task_snapshot", "context_snapshot", "task", "stdout", "summary"}.issubset(retried_types))

        compare = self.client.post(
            f"/api/reviews/{task['id']}/compare",
            json={"runIds": [run_one["id"], run_two["id"]], "title": "harness compare"},
        ).json()
        self.assertEqual(compare["title"], "harness compare")
        self.assertIn("对比 2 个 run", compare["summary"])

        detail_after_compare = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(len(detail_after_compare["reviews"]), 1)

    def test_seed_harness_populates_task_workbench_data(self):
        payload = self.client.post("/api/dev/seed-harness", json={"reset": True}).json()
        self.assertEqual(payload["taskId"], "task-harness-cutover")

        tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "切到 task-first harness")

        detail = self.client.get("/api/tasks/task-harness-cutover").json()
        self.assertEqual(len(detail["refs"]), 2)
        self.assertEqual(len(detail["snapshots"]), 1)
        self.assertEqual(len(detail["runs"]), 2)
        self.assertEqual(len(detail["reviews"]), 1)
        self.assertEqual(detail["metadata"], {})

        artifacts = self.client.get("/api/runs/task-run-2/artifacts").json()["artifacts"]
        self.assertTrue(any(item["type"] == "stdout" for item in artifacts))

    def test_create_task_accepts_metadata_and_refs(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 PR review 评论",
                "description": "把外部评论接回 KAM 任务池。",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "labels": ["dogfood", "github"],
                "metadata": {
                    "recommendedPrompt": "处理评审评论并回推。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_pr_review_comments",
                },
                "refs": [
                    {"kind": "url", "label": "PR", "value": "https://github.com/lusipad/KAM/pull/4518"},
                    {"kind": "file", "label": "Run Engine", "value": "backend/services/run_engine.py"},
                ],
            },
        ).json()

        self.assertEqual(task["priority"], "high")
        self.assertEqual(task["metadata"]["recommendedPrompt"], "处理评审评论并回推。")
        self.assertEqual(task["metadata"]["sourceKind"], "github_pr_review_comments")

        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(len(detail["refs"]), 2)
        self.assertEqual(detail["refs"][0]["label"], "PR")
        self.assertEqual(detail["refs"][1]["value"], "backend/services/run_engine.py")

    def test_create_task_can_attach_dependencies_and_reports_blocking_state(self):
        prerequisite = self.client.post(
            "/api/tasks",
            json={
                "title": "先完成前置任务",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
            },
        ).json()

        task = self.client.post(
            "/api/tasks",
            json={
                "title": "依赖前置任务的实现",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "medium",
                "dependsOnTaskIds": [prerequisite["id"]],
            },
        ).json()

        self.assertFalse(task["dependencyState"]["ready"])
        self.assertEqual(task["dependencyState"]["blockingTaskIds"], [prerequisite["id"]])

        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(detail["dependencyState"]["dependencies"][0]["taskId"], prerequisite["id"])
        self.assertEqual(detail["dependencyState"]["dependencies"][0]["title"], "先完成前置任务")
        self.assertIn("依赖未完成", detail["dependencyState"]["summary"])

    def test_add_dependency_rejects_cycle(self):
        root = self.client.post(
            "/api/tasks",
            json={"title": "根任务", "repoPath": "D:/Repos/KAM", "status": "open", "priority": "high"},
        ).json()
        child = self.client.post(
            "/api/tasks",
            json={
                "title": "子任务",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "medium",
                "dependsOnTaskIds": [root["id"]],
            },
        ).json()

        response = self.client.post(f"/api/tasks/{root['id']}/dependencies", json={"dependsOnTaskId": child["id"]})

        self.assertEqual(response.status_code, 409)
        self.assertIn("不能形成循环", response.json()["detail"])

    def test_create_task_reuses_active_source_task_with_same_dedup_key(self):
        first = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 PR review 评论",
                "description": "第一轮评论。",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "labels": ["dogfood", "github"],
                "metadata": {
                    "recommendedPrompt": "处理第一轮评论。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_pr_review_comments",
                    "sourceDedupKey": "github_pr_review_comments:lusipad/KAM:4518",
                    "sourceRepo": "lusipad/KAM",
                    "sourcePullNumber": 4518,
                    "sourceMeta": {"headRef": "feature/pr-4518"},
                    "sourceReviewComments": [
                        {"id": 1, "body": "请先修第一处", "path": "backend/a.py", "line": 11, "html_url": "https://github.com/lusipad/KAM/pull/4518#discussion_r1"}
                    ],
                },
                "refs": [
                    {
                        "kind": "url",
                        "label": "PR",
                        "value": "https://github.com/lusipad/KAM/pull/4518",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments"},
                    },
                    {
                        "kind": "url",
                        "label": "Review comment #1",
                        "value": "https://github.com/lusipad/KAM/pull/4518#discussion_r1",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments", "commentId": 1},
                    },
                ],
            },
        ).json()

        second = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 PR review 评论",
                "description": "第二轮评论，应该复用同一张任务。",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "labels": ["dogfood", "github", "autodrive"],
                "metadata": {
                    "recommendedPrompt": "处理第二轮评论。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_pr_review_comments",
                    "sourceDedupKey": "github_pr_review_comments:lusipad/KAM:4518",
                    "sourceRepo": "lusipad/KAM",
                    "sourcePullNumber": 4518,
                    "sourceMeta": {"headRef": "feature/pr-4518"},
                    "sourceReviewComments": [
                        {"id": 2, "body": "再补第二处", "path": "backend/b.py", "line": 22, "html_url": "https://github.com/lusipad/KAM/pull/4518#discussion_r2"}
                    ],
                },
                "refs": [
                    {
                        "kind": "url",
                        "label": "PR",
                        "value": "https://github.com/lusipad/KAM/pull/4518",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments"},
                    },
                    {
                        "kind": "url",
                        "label": "Review comment #2",
                        "value": "https://github.com/lusipad/KAM/pull/4518#discussion_r2",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments", "commentId": 2},
                    },
                ],
            },
        ).json()

        self.assertEqual(second["id"], first["id"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(len(tasks[0]["metadata"]["sourceReviewComments"]), 2)
        self.assertIn("backend/a.py", tasks[0]["metadata"]["recommendedPrompt"])
        self.assertIn("backend/b.py", tasks[0]["metadata"]["recommendedPrompt"])
        self.assertIn("autodrive", tasks[0]["labels"])

        detail = self.client.get(f"/api/tasks/{first['id']}").json()
        self.assertIn("请先修第一处", detail["description"])
        self.assertIn("再补第二处", detail["description"])
        self.assertEqual(len(detail["refs"]), 3)
        self.assertEqual(
            [item["label"] for item in detail["refs"]],
            ["PR", "Review comment #1", "Review comment #2"],
        )

    def test_create_task_reuses_active_github_issue_source_task_with_same_dedup_key(self):
        first = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 GitHub Issue",
                "description": "第一轮 issue 描述。",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "labels": ["github", "issue"],
                "metadata": {
                    "recommendedPrompt": "处理第一轮 issue。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_issue",
                    "sourceDedupKey": "github_issue:lusipad/KAM:4519",
                    "sourceRepo": "lusipad/KAM",
                    "sourceIssueNumber": 4519,
                    "sourceIssueTitle": "UI 首屏太难理解",
                    "sourceIssueBody": "希望用户第一次打开就知道当前状态、下一步和入口。",
                    "sourceIssueComments": [
                        {
                            "id": 7001,
                            "body": "最好默认就是新手视角。",
                            "user": "reviewer",
                            "html_url": "https://github.com/lusipad/KAM/issues/4519#issuecomment-7001",
                        }
                    ],
                },
                "refs": [
                    {
                        "kind": "url",
                        "label": "Issue",
                        "value": "https://github.com/lusipad/KAM/issues/4519",
                        "metadata": {"intakeSourceKind": "github_issue"},
                    },
                    {
                        "kind": "url",
                        "label": "Issue comment #7001",
                        "value": "https://github.com/lusipad/KAM/issues/4519#issuecomment-7001",
                        "metadata": {"intakeSourceKind": "github_issue", "commentId": 7001},
                    },
                ],
            },
        ).json()

        second = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 GitHub Issue",
                "description": "第二轮 issue 更新。",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "labels": ["github", "issue", "autodrive"],
                "metadata": {
                    "recommendedPrompt": "处理第二轮 issue。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_issue",
                    "sourceDedupKey": "github_issue:lusipad/KAM:4519",
                    "sourceRepo": "lusipad/KAM",
                    "sourceIssueNumber": 4519,
                    "sourceIssueTitle": "UI 首屏太难理解",
                    "sourceIssueBody": "希望用户第一次打开就知道当前状态、下一步和入口。",
                    "sourceIssueComments": [
                        {
                            "id": 7002,
                            "body": "还要告诉我当前系统在干什么。",
                            "user": "lus",
                            "html_url": "https://github.com/lusipad/KAM/issues/4519#issuecomment-7002",
                        }
                    ],
                },
                "refs": [
                    {
                        "kind": "url",
                        "label": "Issue",
                        "value": "https://github.com/lusipad/KAM/issues/4519",
                        "metadata": {"intakeSourceKind": "github_issue"},
                    },
                    {
                        "kind": "url",
                        "label": "Issue comment #7002",
                        "value": "https://github.com/lusipad/KAM/issues/4519#issuecomment-7002",
                        "metadata": {"intakeSourceKind": "github_issue", "commentId": 7002},
                    },
                ],
            },
        ).json()

        self.assertEqual(second["id"], first["id"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(len(tasks[0]["metadata"]["sourceIssueComments"]), 2)
        self.assertIn("UI 首屏太难理解", tasks[0]["metadata"]["recommendedPrompt"])
        self.assertIn("当前系统在干什么", tasks[0]["metadata"]["recommendedPrompt"])
        self.assertIn("autodrive", tasks[0]["labels"])

        detail = self.client.get(f"/api/tasks/{first['id']}").json()
        self.assertIn("Issue 标题", detail["description"])
        self.assertIn("最好默认就是新手视角", detail["description"])
        self.assertIn("当前系统在干什么", detail["description"])
        self.assertEqual(len(detail["refs"]), 3)
        self.assertEqual(
            [item["label"] for item in detail["refs"]],
            ["Issue", "Issue comment #7001", "Issue comment #7002"],
        )

    def test_create_task_creates_follow_up_when_same_source_task_is_already_running(self):
        first = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 PR review 评论",
                "description": "首轮评论已经开始处理。",
                "repoPath": "D:/Repos/KAM",
                "status": "in_progress",
                "priority": "high",
                "labels": ["dogfood", "github"],
                "metadata": {
                    "recommendedPrompt": "处理首轮评论。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_pr_review_comments",
                    "sourceDedupKey": "github_pr_review_comments:lusipad/KAM:4518",
                    "sourceRepo": "lusipad/KAM",
                    "sourcePullNumber": 4518,
                    "sourceMeta": {"headRef": "feature/pr-4518"},
                    "sourceReviewComments": [
                        {"id": 1, "body": "请先修第一处", "path": "backend/a.py", "line": 11, "html_url": "https://github.com/lusipad/KAM/pull/4518#discussion_r1"}
                    ],
                },
                "refs": [
                    {
                        "kind": "url",
                        "label": "PR",
                        "value": "https://github.com/lusipad/KAM/pull/4518",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments"},
                    },
                    {
                        "kind": "url",
                        "label": "Review comment #1",
                        "value": "https://github.com/lusipad/KAM/pull/4518#discussion_r1",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments", "commentId": 1},
                    },
                ],
            },
        ).json()
        asyncio.run(self._seed_running_run(first["id"]))

        second = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 PR review 评论",
                "description": "第二轮评论应该进入后继任务。",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "labels": ["dogfood", "github", "follow-up"],
                "metadata": {
                    "recommendedPrompt": "处理第二轮评论。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_pr_review_comments",
                    "sourceDedupKey": "github_pr_review_comments:lusipad/KAM:4518",
                    "sourceRepo": "lusipad/KAM",
                    "sourcePullNumber": 4518,
                    "sourceMeta": {"headRef": "feature/pr-4518"},
                    "sourceReviewComments": [
                        {"id": 2, "body": "再补第二处", "path": "backend/b.py", "line": 22, "html_url": "https://github.com/lusipad/KAM/pull/4518#discussion_r2"}
                    ],
                },
                "refs": [
                    {
                        "kind": "url",
                        "label": "PR",
                        "value": "https://github.com/lusipad/KAM/pull/4518",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments"},
                    },
                    {
                        "kind": "url",
                        "label": "Review comment #2",
                        "value": "https://github.com/lusipad/KAM/pull/4518#discussion_r2",
                        "metadata": {"intakeSourceKind": "github_pr_review_comments", "commentId": 2},
                    },
                ],
            },
        ).json()

        self.assertNotEqual(second["id"], first["id"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(tasks), 2)

        first_detail = self.client.get(f"/api/tasks/{first['id']}").json()
        second_detail = self.client.get(f"/api/tasks/{second['id']}").json()
        self.assertEqual(first_detail["metadata"]["recommendedPrompt"], "处理首轮评论。")
        self.assertEqual(first_detail["refs"][1]["label"], "Review comment #1")
        self.assertEqual(first_detail["runs"][0]["status"], "running")
        self.assertEqual(second_detail["metadata"]["sourceReviewComments"][0]["id"], 2)
        self.assertEqual(second_detail["refs"][1]["label"], "Review comment #2")
        self.assertIn("follow-up", second_detail["labels"])

    def test_create_task_run_waits_for_source_lock_before_inserting_run(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 PR review 评论",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "metadata": {
                    "recommendedPrompt": "处理评论。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_pr_review_comments",
                    "sourceDedupKey": "github_pr_review_comments:lusipad/KAM:4518",
                    "sourceRepo": "lusipad/KAM",
                    "sourcePullNumber": 4518,
                    "sourceReviewComments": [
                        {"id": 1, "body": "请先修第一处", "path": "backend/a.py", "line": 11},
                    ],
                },
            },
        ).json()

        async def fake_execute_task_run(_self, _run_id: str) -> None:
            return None

        async def scenario() -> None:
            with patch("services.run_engine.RunEngine._execute_task_run", new=fake_execute_task_run):
                async with source_task_guard("github_pr_review_comments:lusipad/KAM:4518"):
                    async def worker() -> None:
                        async with async_session() as session:
                            engine_instance = RunEngine(session)
                            await engine_instance.create_task_run(task_id=task["id"], agent="codex", task="处理评论")

                    worker_task = asyncio.create_task(worker())
                    await asyncio.sleep(0.05)
                    async with engine.begin() as conn:
                        count = (
                            await conn.execute(
                                text("SELECT COUNT(*) FROM task_runs WHERE task_id = :task_id"),
                                {"task_id": task["id"]},
                            )
                        ).scalar_one()
                    self.assertEqual(count, 0)
                await worker_task

            async with engine.begin() as conn:
                count = (
                    await conn.execute(
                        text("SELECT COUNT(*) FROM task_runs WHERE task_id = :task_id"),
                        {"task_id": task["id"]},
                    )
                ).scalar_one()
            self.assertEqual(count, 1)

        asyncio.run(scenario())

    def test_seed_harness_reset_waits_for_background_runs(self):
        calls: list[str] = []

        async def fake_wait_for_background_runs(timeout: float = 5.0):
            calls.append(f"timeout={timeout}")

        with patch("api.dev.wait_for_background_runs", new=fake_wait_for_background_runs):
            response = self.client.post("/api/dev/seed-harness", json={"reset": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ["timeout=5.0"])

    def test_dispatch_next_plans_then_runs_child_task(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：dispatch next"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": True})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "planned_task")
        self.assertEqual(payload["plannedFromTaskId"], "task-harness-cutover")
        self.assertEqual(payload["task"]["status"], "in_progress")
        self.assertEqual(payload["run"]["status"], "passed")
        self.assertEqual(payload["run"]["taskId"], payload["task"]["id"])
        self.assertEqual(payload["task"]["metadata"]["parentTaskId"], "task-harness-cutover")

        detail = self.client.get(f"/api/tasks/{payload['task']['id']}").json()
        self.assertEqual(detail["status"], "in_progress")
        self.assertEqual(len(detail["runs"]), 1)

    def test_dispatch_next_prefers_existing_runnable_child_task(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})
        planned = self.client.post(
            "/api/tasks/task-harness-cutover/plan",
            json={"createTasks": True, "limit": 2},
        ).json()
        child_ids = [item["id"] for item in planned["tasks"]]

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：existing child dispatch"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "existing_task")
        self.assertIn(payload["task"]["id"], child_ids)
        self.assertEqual(payload["run"]["status"], "passed")
        self.assertEqual(payload["task"]["metadata"]["parentTaskId"], "task-harness-cutover")

    def test_dispatch_next_prefers_failed_root_task_over_generic_child_follow_up(self):
        root_task_id = asyncio.run(self._seed_failed_root_with_generic_child())

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：failed root first"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "existing_task")
        self.assertEqual(payload["task"]["id"], root_task_id)
        self.assertEqual(payload["run"]["status"], "passed")

    def test_dispatch_next_returns_conflict_when_no_task_available(self):
        response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": False})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "当前没有可自动接手的任务")

    def test_dispatch_next_can_push_back_to_tracked_remote_branch(self):
        repo, remote, branch_name = self._create_remote_backed_git_repo()
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "处理远端分支上的评审修复",
                "repoPath": str(repo),
                "status": "open",
                "priority": "high",
                "labels": ["dogfood", "github", "pr-review"],
                "metadata": {
                    "recommendedPrompt": "更新 README 并验证，再把结果推回评审分支。",
                    "recommendedAgent": "codex",
                    "executionRemoteUrl": str(remote),
                    "executionRef": branch_name,
                    "executionPushOnSuccess": True,
                    "sourceKind": "github_pr_review_comments",
                    "sourceRepo": "lusipad/KAM",
                    "sourcePullNumber": 4518,
                    "sourceMeta": {"headRef": branch_name},
                    "sourceReviewComments": [{"id": 9, "path": "README.md", "body": "Please update README"}],
                },
                "refs": [
                    {"kind": "url", "label": "PR", "value": "https://github.com/lusipad/KAM/pull/4518"},
                    {"kind": "file", "label": "README", "value": "README.md"},
                ],
            },
        ).json()

        async def fake_run_command(_engine, _command, cwd):
            readme = Path(cwd) / "README.md"
            readme.write_text("after remote push\n", encoding="utf-8")
            return 0, "执行完成：已回推到评审分支"

        with patch("services.run_engine.RunEngine._run_command", new=fake_run_command):
            response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task"]["id"], task["id"])
        self.assertEqual(payload["run"]["status"], "passed")
        self.assertIsNotNone(payload["run"]["adoptedAt"])

        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(detail["status"], "verified")

        self._git(repo, "fetch", "origin", branch_name)
        pushed_readme = self._git_output(repo, "show", "FETCH_HEAD:README.md")
        self.assertEqual(pushed_readme, "after remote push\n")

        artifacts = self.client.get(f"/api/runs/{payload['run']['id']}/artifacts").json()["artifacts"]
        self.assertTrue(any(item["type"] == "source_context" for item in artifacts))

    def test_build_task_initial_artifacts_include_github_issue_source_context(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "处理 GitHub Issue",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "labels": ["github", "issue"],
                "metadata": {
                    "recommendedPrompt": "先看 issue 再决定是否修改代码。",
                    "recommendedAgent": "codex",
                    "sourceKind": "github_issue",
                    "sourceRepo": "lusipad/KAM",
                    "sourceIssueNumber": 4519,
                    "sourceIssueTitle": "UI 首屏太难理解",
                    "sourceIssueBody": "希望用户第一次打开就知道当前状态、下一步和入口。",
                    "sourceIssueComments": [
                        {
                            "id": 7001,
                            "body": "最好默认就是新手视角。",
                            "user": "reviewer",
                            "html_url": "https://github.com/lusipad/KAM/issues/4519#issuecomment-7001",
                        }
                    ],
                },
            },
        ).json()

        async def build_artifacts() -> list[dict[str, object]]:
            async with async_session() as session:
                return await RunEngine(session).build_task_initial_artifacts(task["id"])

        artifacts = asyncio.run(build_artifacts())
        source_context = next(item for item in artifacts if item["type"] == "source_context")
        payload = json.loads(source_context["content"])

        self.assertEqual(payload["sourceKind"], "github_issue")
        self.assertEqual(payload["sourceRepo"], "lusipad/KAM")
        self.assertEqual(payload["sourceIssueNumber"], 4519)
        self.assertEqual(payload["sourceIssueTitle"], "UI 首屏太难理解")
        self.assertEqual(payload["sourceIssueComments"][0]["id"], 7001)

    def test_dispatch_next_skips_task_with_unresolved_dependencies(self):
        prerequisite = self.client.post(
            "/api/tasks",
            json={"title": "前置任务", "repoPath": "D:/Repos/KAM", "status": "open", "priority": "high"},
        ).json()
        blocked = self.client.post(
            "/api/tasks",
            json={
                "title": "被依赖阻塞的任务",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "high",
                "dependsOnTaskIds": [prerequisite["id"]],
                "metadata": {
                    "recommendedPrompt": "这张任务现在不该被执行。",
                    "recommendedAgent": "codex",
                    "acceptanceChecks": ["noop"],
                    "suggestedRefs": [],
                },
            },
        ).json()
        ready = self.client.post(
            "/api/tasks",
            json={
                "title": "可直接执行的任务",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "medium",
                "metadata": {
                    "recommendedPrompt": "优先执行这张 ready 任务。",
                    "recommendedAgent": "codex",
                    "acceptanceChecks": ["执行 ready task"],
                    "suggestedRefs": [],
                },
            },
        ).json()

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：ready task"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task"]["id"], ready["id"])
        self.assertNotEqual(payload["task"]["id"], blocked["id"])

    def test_continue_prefers_adopt_for_latest_passed_unadopted_run(self):
        repo = self._create_git_repo()
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "自动采纳最新通过 run",
                "repoPath": str(repo),
                "status": "in_progress",
                "priority": "high",
            },
        ).json()

        async def fake_run_command(_engine, _command, cwd):
            readme = Path(cwd) / "README.md"
            readme.write_text("after\n", encoding="utf-8")
            return 0, "执行完成：可以自动 adopt"

        with patch("services.run_engine.RunEngine._run_command", new=fake_run_command):
            run = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "codex", "task": "更新 README 并准备采纳"},
            ).json()

        response = self.client.post(
            "/api/tasks/continue",
            json={"taskId": task["id"], "createPlanIfNeeded": True},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["action"], "adopt")
        self.assertEqual(payload["reason"], "latest_passed_run_adopted")
        self.assertIn("已采纳最近通过的 run", payload["summary"])
        self.assertEqual(payload["task"]["id"], task["id"])
        self.assertEqual(payload["run"]["id"], run["id"])
        self.assertIsNotNone(payload["run"]["adoptedAt"])
        self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "after\n")

    def test_continue_prefers_adopt_before_retry_when_both_are_available(self):
        repo = self._create_git_repo()
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "先采纳已通过结果，再回头补失败修复",
                "repoPath": str(repo),
                "status": "in_progress",
                "priority": "high",
            },
        ).json()

        async def fake_run_command(_engine, _command, cwd):
            readme = Path(cwd) / "README.md"
            readme.write_text("after adopt first\n", encoding="utf-8")
            return 0, "执行完成：先产出可采纳结果"

        with patch("services.run_engine.RunEngine._run_command", new=fake_run_command):
            passed_run = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "codex", "task": "先产出一轮可以直接采纳的改动"},
            ).json()

        asyncio.run(self._seed_retryable_child_for_parent(task["id"]))

        response = self.client.post(
            "/api/tasks/continue",
            json={"taskId": task["id"], "createPlanIfNeeded": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "adopt")
        self.assertEqual(payload["reason"], "latest_passed_run_adopted")
        self.assertEqual(payload["task"]["id"], task["id"])
        self.assertEqual(payload["run"]["id"], passed_run["id"])
        self.assertIsNotNone(payload["run"]["adoptedAt"])
        self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "after adopt first\n")

    def test_continue_retries_latest_failed_child_run_before_planning_new_work(self):
        parent_task_id, child_task_id = asyncio.run(self._seed_retryable_child_task())

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：child retry"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post(
                "/api/tasks/continue",
                json={"taskId": parent_task_id, "createPlanIfNeeded": True},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "retry")
        self.assertEqual(payload["reason"], "latest_failed_run_retried")
        self.assertIn("已自动重试最近失败的 run", payload["summary"])
        self.assertEqual(payload["task"]["id"], child_task_id)
        self.assertEqual(payload["run"]["status"], "passed")

    def test_continue_retries_latest_failed_run_for_current_task(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "直接重试当前失败任务",
                "repoPath": "D:/Repos/KAM",
                "status": "failed",
                "priority": "high",
            },
        ).json()
        self.client.patch(
            f"/api/tasks/{task['id']}",
            json={
                "status": "failed",
                "priority": "high",
            },
        )
        asyncio.run(self._seed_retryable_root_task(task["id"]))

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：root retry"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post(
                "/api/tasks/continue",
                json={"taskId": task["id"], "createPlanIfNeeded": True},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "retry")
        self.assertEqual(payload["reason"], "latest_failed_run_retried")
        self.assertEqual(payload["task"]["id"], task["id"])
        self.assertEqual(payload["run"]["status"], "passed")

    def test_continue_stops_when_latest_failed_run_reaches_retry_budget(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "失败预算耗尽后停止自动继续",
                "repoPath": "D:/Repos/KAM",
                "status": "failed",
                "priority": "high",
            },
        ).json()
        asyncio.run(self._seed_retry_exhausted_root_task(task["id"]))

        response = self.client.post(
            "/api/tasks/continue",
            json={"taskId": task["id"], "createPlanIfNeeded": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "stop")
        self.assertEqual(payload["reason"], "latest_failed_run_retry_budget_exhausted")
        self.assertIn("已达到自动重试上限", payload["summary"])
        self.assertEqual(payload["task"]["id"], task["id"])
        self.assertEqual(payload["run"]["id"], "runrootx002")

    def test_dispatch_next_skips_failed_task_when_retry_budget_is_exhausted(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "失败预算耗尽后不再自动开跑",
                "repoPath": "D:/Repos/KAM",
                "status": "failed",
                "priority": "high",
            },
        ).json()
        asyncio.run(self._seed_retry_exhausted_root_task(task["id"]))

        response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": False})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "当前没有可自动接手的任务")

    def test_continue_plans_and_dispatches_when_parent_has_no_runnable_child(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：continue dispatch"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post(
                "/api/tasks/continue",
                json={"taskId": "task-harness-cutover", "createPlanIfNeeded": True},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "plan_and_dispatch")
        self.assertEqual(payload["source"], "planned_task")
        self.assertIn("已先拆后跑", payload["summary"])
        self.assertEqual(payload["plannedFromTaskId"], "task-harness-cutover")
        self.assertEqual(payload["task"]["metadata"]["parentTaskId"], "task-harness-cutover")
        self.assertEqual(payload["run"]["status"], "passed")

    def test_continue_stops_when_task_is_terminal(self):
        task_id = asyncio.run(self._seed_terminal_task())

        response = self.client.post("/api/tasks/continue", json={"taskId": task_id, "createPlanIfNeeded": True})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "stop")
        self.assertEqual(payload["reason"], "scope_task_terminal")
        self.assertIn("已经收口", payload["summary"])
        self.assertEqual(payload["task"]["id"], task_id)

    def test_continue_stops_when_scope_has_active_run(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "等待当前执行结束",
                "repoPath": "D:/Repos/KAM",
                "status": "in_progress",
                "priority": "high",
            },
        ).json()

        asyncio.run(self._seed_running_run(task["id"]))

        response = self.client.post("/api/tasks/continue", json={"taskId": task["id"], "createPlanIfNeeded": True})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "stop")
        self.assertEqual(payload["reason"], "scope_has_active_run")
        self.assertIn("还有 run 在执行", payload["summary"])
        self.assertEqual(payload["task"]["id"], task["id"])

    def test_continue_stops_when_scope_dependencies_unresolved(self):
        prerequisite = self.client.post(
            "/api/tasks",
            json={"title": "前置任务", "repoPath": "D:/Repos/KAM", "status": "open", "priority": "high"},
        ).json()
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "等待前置任务的 root",
                "repoPath": "D:/Repos/KAM",
                "status": "in_progress",
                "priority": "high",
                "dependsOnTaskIds": [prerequisite["id"]],
            },
        ).json()

        response = self.client.post("/api/tasks/continue", json={"taskId": task["id"], "createPlanIfNeeded": True})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], "stop")
        self.assertEqual(payload["reason"], "scope_dependencies_unresolved")
        self.assertIn("依赖未完成", payload["summary"])

    def test_autodrive_start_advances_task_family_until_no_high_value_action(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：auto drive"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/task-harness-cutover/autodrive/start")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scopeTaskId"], "task-harness-cutover")
        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["running"])
        self.assertIn("已开启当前任务族的自动托管", payload["summary"])

        root_detail = self.client.get("/api/tasks/task-harness-cutover").json()
        root_metadata = root_detail["metadata"]
        self.assertTrue(root_metadata["autoDriveEnabled"])
        self.assertEqual(root_metadata["autoDriveStatus"], "idle")
        self.assertEqual(root_metadata["autoDriveLastAction"], "stop")
        self.assertEqual(root_metadata["autoDriveLastReason"], "no_high_value_action")
        self.assertGreaterEqual(root_metadata["autoDriveLoopCount"], 2)
        self.assertGreaterEqual(len(root_metadata["autoDriveRecentEvents"]), 1)
        self.assertTrue(any(item["reason"] == "no_high_value_action" for item in root_metadata["autoDriveRecentEvents"]))

        tasks = self.client.get("/api/tasks").json()["tasks"]
        child_tasks = [item for item in tasks if item["metadata"].get("parentTaskId") == "task-harness-cutover"]
        self.assertGreaterEqual(len(child_tasks), 2)
        self.assertTrue(all(item["status"] == "in_progress" for item in child_tasks))
        for item in child_tasks:
            detail = self.client.get(f"/api/tasks/{item['id']}").json()
            self.assertTrue(detail["runs"])
            self.assertEqual(detail["runs"][-1]["status"], "passed")

    def test_autodrive_pauses_when_latest_failed_run_reaches_retry_budget(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "失败预算耗尽后暂停自动托管",
                "repoPath": "D:/Repos/KAM",
                "status": "failed",
                "priority": "high",
            },
        ).json()
        asyncio.run(self._seed_retry_exhausted_root_task(task["id"]))

        response = self.client.post(f"/api/tasks/{task['id']}/autodrive/start")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scopeTaskId"], task["id"])
        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["running"])

        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(detail["metadata"]["autoDriveStatus"], "paused")
        self.assertEqual(detail["metadata"]["autoDriveLastAction"], "stop")
        self.assertEqual(detail["metadata"]["autoDriveLastReason"], "latest_failed_run_retry_budget_exhausted")

    def test_global_autodrive_start_advances_across_task_families(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})
        second_root_id = asyncio.run(self._seed_secondary_root_task())

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：global auto drive"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/autodrive/global/start")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["running"])
        self.assertIn("已开启全局无人值守", payload["summary"])

        status = self.client.get("/api/tasks/autodrive/global").json()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["status"], "idle")
        self.assertEqual(status["lastAction"], "stop")
        self.assertEqual(status["lastReason"], "no_high_value_action")
        self.assertGreaterEqual(status["loopCount"], 3)
        self.assertGreaterEqual(len(status["recentEvents"]), 1)
        self.assertTrue(any(item["reason"] == "no_high_value_action" for item in status["recentEvents"]))

        tasks = self.client.get("/api/tasks").json()["tasks"]
        root_one_children = [item for item in tasks if item["metadata"].get("parentTaskId") == "task-harness-cutover"]
        root_two_children = [item for item in tasks if item["metadata"].get("parentTaskId") == second_root_id]
        self.assertGreaterEqual(len(root_one_children), 2)
        self.assertGreaterEqual(len(root_two_children), 1)
        self.assertTrue(all(item["status"] == "in_progress" for item in root_two_children))
        for item in root_two_children:
            detail = self.client.get(f"/api/tasks/{item['id']}").json()
            self.assertTrue(detail["runs"])
            self.assertEqual(detail["runs"][-1]["status"], "passed")

    def test_global_autodrive_stop_disables_supervisor(self):
        start_response = self.client.post("/api/tasks/autodrive/global/start")
        self.assertEqual(start_response.status_code, 200)

        response = self.client.post("/api/tasks/autodrive/global/stop")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["running"])
        self.assertEqual(payload["status"], "disabled")
        self.assertEqual(payload["lastReason"], "global_auto_drive_stopped")
        self.assertEqual(payload["currentTaskId"], None)
        self.assertIn("已停止全局无人值守", payload["summary"])

        status = self.client.get("/api/tasks/autodrive/global").json()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["status"], "disabled")

    def test_global_autodrive_waits_when_foreign_lease_is_active(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})
        second_root_id = asyncio.run(self._seed_secondary_root_task())
        self._write_foreign_global_lease(stale=False)

        response = self.client.post("/api/tasks/autodrive/global/start")

        self.assertEqual(response.status_code, 200)
        status = self.client.get("/api/tasks/autodrive/global").json()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["status"], "waiting_for_lease")
        self.assertEqual(status["lastReason"], "global_auto_drive_lease_held_by_other_process")
        self.assertIsNotNone(status["updatedAt"])
        self.assertEqual(status["lease"]["hostname"], "foreign-host")
        self.assertEqual(status["lease"]["pid"], 4321)
        self.assertFalse(status["lease"]["ownedByCurrentProcess"])
        self.assertFalse(status["lease"]["stale"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        root_two_children = [item for item in tasks if item["metadata"].get("parentTaskId") == second_root_id]
        self.assertEqual(root_two_children, [])

    def test_global_autodrive_reclaims_stale_foreign_lease(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})
        second_root_id = asyncio.run(self._seed_secondary_root_task())
        self._write_foreign_global_lease(stale=True)

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：stale lease reclaim"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/autodrive/global/start")

        self.assertEqual(response.status_code, 200)
        status = self.client.get("/api/tasks/autodrive/global").json()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["status"], "idle")
        self.assertEqual(status["lastReason"], "no_high_value_action")
        self.assertTrue(status["lease"]["ownedByCurrentProcess"])
        self.assertFalse(status["lease"]["stale"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        root_two_children = [item for item in tasks if item["metadata"].get("parentTaskId") == second_root_id]
        self.assertGreaterEqual(len(root_two_children), 1)

        lease_payload = self._read_global_lease_payload()
        self.assertIsNotNone(lease_payload)
        self.assertEqual(lease_payload["pid"], os.getpid())

    def test_seed_harness_reset_clears_global_autodrive_runtime_state(self):
        self.client.post("/api/tasks/autodrive/global/start")
        self._write_foreign_global_lease(stale=False)

        response = self.client.post("/api/dev/seed-harness", json={"reset": True})

        self.assertEqual(response.status_code, 200)
        status = self.client.get("/api/tasks/autodrive/global").json()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["status"], "disabled")
        self.assertEqual(status["summary"], "当前还没有开启全局无人值守。")
        self.assertFalse((TMP_ROOT / GLOBAL_AUTO_DRIVE_LEASE_FILENAME).exists())

    def test_startup_recovers_persisted_global_autodrive_after_restart(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})
        second_root_id = asyncio.run(self._seed_secondary_root_task())

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：restart recovery"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            start_response = self.client.post("/api/tasks/autodrive/global/start")
            self.assertEqual(start_response.status_code, 200)

            self._restart_client(clear_persistence=False)

            status = self.client.get("/api/tasks/autodrive/global").json()

        self.assertTrue(status["enabled"])
        self.assertEqual(status["status"], "idle")
        self.assertEqual(status["lastReason"], "no_high_value_action")
        self.assertGreaterEqual(len(status["recentEvents"]), 1)
        self.assertTrue(any(item["reason"] in {"global_auto_drive_recovered", "no_high_value_action"} for item in status["recentEvents"]))

        tasks = self.client.get("/api/tasks").json()["tasks"]
        root_two_children = [item for item in tasks if item["metadata"].get("parentTaskId") == second_root_id]
        self.assertGreaterEqual(len(root_two_children), 1)

    def test_startup_recovers_persisted_global_autodrive_and_reclaims_stale_lease(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})
        second_root_id = asyncio.run(self._seed_secondary_root_task())
        self._write_persisted_global_autodrive_state()
        self._write_foreign_global_lease(age_seconds=30.0)

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：restart reclaim stale lease"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            self._restart_client(clear_persistence=False)
            status = self.client.get("/api/tasks/autodrive/global").json()

        self.assertTrue(status["enabled"])
        self.assertEqual(status["status"], "idle")
        self.assertEqual(status["lastReason"], "no_high_value_action")
        self.assertTrue(status["lease"]["ownedByCurrentProcess"])
        self.assertFalse(status["lease"]["stale"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        root_two_children = [item for item in tasks if item["metadata"].get("parentTaskId") == second_root_id]
        self.assertGreaterEqual(len(root_two_children), 1)

    def test_startup_waits_for_foreign_lease_then_reclaims_after_ttl_on_next_restart(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})
        second_root_id = asyncio.run(self._seed_secondary_root_task())
        self._write_persisted_global_autodrive_state()

        ttl_seconds = 2.0
        self._write_foreign_global_lease(age_seconds=0.1)

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：restart reclaim after ttl"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.task_autodrive.GLOBAL_AUTO_DRIVE_LEASE_TTL_SECONDS", new=ttl_seconds),
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            self._restart_client(clear_persistence=False)
            waiting_status = self.client.get("/api/tasks/autodrive/global").json()

            self.assertTrue(waiting_status["enabled"])
            self.assertEqual(waiting_status["status"], "waiting_for_lease")
            self.assertEqual(waiting_status["lastReason"], "global_auto_drive_lease_held_by_other_process")
            self.assertFalse(waiting_status["lease"]["ownedByCurrentProcess"])
            self.assertFalse(waiting_status["lease"]["stale"])

            tasks = self.client.get("/api/tasks").json()["tasks"]
            root_two_children = [item for item in tasks if item["metadata"].get("parentTaskId") == second_root_id]
            self.assertEqual(root_two_children, [])

            time.sleep(ttl_seconds + 0.4)

            self._restart_client(clear_persistence=False)
            recovered_status = self.client.get("/api/tasks/autodrive/global").json()

        self.assertTrue(recovered_status["enabled"])
        self.assertEqual(recovered_status["status"], "idle")
        self.assertEqual(recovered_status["lastReason"], "no_high_value_action")
        self.assertTrue(recovered_status["lease"]["ownedByCurrentProcess"])
        self.assertFalse(recovered_status["lease"]["stale"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        root_two_children = [item for item in tasks if item["metadata"].get("parentTaskId") == second_root_id]
        self.assertGreaterEqual(len(root_two_children), 1)

    def test_global_autodrive_recovers_after_dispatch_exception(self):
        async def scenario():
            attempts = 0

            async def flaky_continue_task(_service, *, task_id, create_plan_if_needed):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("dispatcher boom")
                return SimpleNamespace(
                    action="stop",
                    reason="no_high_value_action",
                    summary="已恢复并回到轮询空闲。",
                    task=None,
                    scope_task_id=None,
                    run=None,
                    error=None,
                )

            with (
                patch.object(type(config.settings), "is_test_env", new_callable=PropertyMock, return_value=False),
                patch("services.task_autodrive.GLOBAL_AUTO_DRIVE_POLL_INTERVAL_SECONDS", new=0.05),
                patch("services.task_dispatcher.TaskDispatcherService.continue_task", new=flaky_continue_task),
            ):
                service = GlobalAutoDriveService()
                start_result = await service.start()
                self.assertTrue(start_result.enabled)

                deadline = asyncio.get_running_loop().time() + 1.5
                status = None
                while asyncio.get_running_loop().time() < deadline:
                    status = await service.get_status()
                    if status.status == "idle" and status.last_reason == "no_high_value_action" and attempts >= 2:
                        break
                    await asyncio.sleep(0.05)
                else:
                    self.fail("global autodrive did not recover after dispatch exception")

                self.assertIsNotNone(status)
                self.assertEqual(status.status, "idle")
                self.assertEqual(status.last_reason, "no_high_value_action")
                self.assertGreaterEqual(attempts, 2)
                self.assertFalse(status.error)

                stop_result = await service.stop()
                self.assertFalse(stop_result.enabled)

        asyncio.run(scenario())

    def test_global_autodrive_recovers_after_dispatch_timeout(self):
        async def scenario():
            attempts = 0

            async def slow_then_stop(_service, *, task_id, create_plan_if_needed):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    await asyncio.sleep(0.15)
                return SimpleNamespace(
                    action="stop",
                    reason="no_high_value_action",
                    summary="已恢复并回到轮询空闲。",
                    task=None,
                    scope_task_id=None,
                    run=None,
                    error=None,
                )

            with (
                patch.object(type(config.settings), "is_test_env", new_callable=PropertyMock, return_value=False),
                patch("services.task_autodrive.GLOBAL_AUTO_DRIVE_POLL_INTERVAL_SECONDS", new=0.05),
                patch("services.task_autodrive.GLOBAL_AUTO_DRIVE_DECISION_TIMEOUT_SECONDS", new=0.05),
                patch("services.task_dispatcher.TaskDispatcherService.continue_task", new=slow_then_stop),
            ):
                service = GlobalAutoDriveService()
                start_result = await service.start()
                self.assertTrue(start_result.enabled)

                deadline = asyncio.get_running_loop().time() + 1.5
                status = None
                while asyncio.get_running_loop().time() < deadline:
                    status = await service.get_status()
                    if status.status == "idle" and status.last_reason == "no_high_value_action" and attempts >= 2:
                        break
                    await asyncio.sleep(0.05)
                else:
                    self.fail("global autodrive did not recover after dispatch timeout")

                self.assertIsNotNone(status)
                self.assertEqual(status.status, "idle")
                self.assertEqual(status.last_reason, "no_high_value_action")
                self.assertGreaterEqual(attempts, 2)
                self.assertFalse(status.error)
                self.assertTrue(any(item["reason"] == "global_auto_drive_dispatch_timeout" for item in status.recent_events))

                stop_result = await service.stop()
                self.assertFalse(stop_result.enabled)

        asyncio.run(scenario())

    def test_global_autodrive_lease_blocks_second_process_until_owner_releases(self):
        owner = self._spawn_global_lease_probe_process(sleep_seconds=3.0, release_on_exit=True)
        try:
            first = self._read_global_lease_probe_result(owner)
            self.assertTrue(first["acquired"])
            self.assertTrue(first["lease"]["ownedByCurrentProcess"])

            contender = self._run_global_lease_probe_process()
            self.assertFalse(contender["acquired"])
            self.assertEqual(contender["lease"]["hostname"], first["lease"]["hostname"])
            self.assertEqual(contender["lease"]["pid"], first["lease"]["pid"])
            self.assertFalse(contender["lease"]["ownedByCurrentProcess"])

            owner.wait(timeout=5)
            self.assertEqual(owner.returncode, 0)

            takeover = self._run_global_lease_probe_process()
            self.assertTrue(takeover["acquired"])
            self.assertTrue(takeover["lease"]["ownedByCurrentProcess"])
        finally:
            self._cleanup_global_lease_probe_process(owner, force_kill=False)

    def test_global_autodrive_reclaims_crashed_owner_after_ttl(self):
        ttl_seconds = 4.0
        owner = self._spawn_global_lease_probe_process(
            sleep_seconds=30.0,
            release_on_exit=False,
            ttl_seconds=ttl_seconds,
        )
        try:
            first = self._read_global_lease_probe_result(owner)
            self.assertTrue(first["acquired"])
            owner_pid = first["lease"]["pid"]

            owner.kill()
            owner.wait(timeout=5)

            blocked = self._run_global_lease_probe_process(ttl_seconds=ttl_seconds)
            self.assertFalse(blocked["acquired"])
            self.assertEqual(blocked["lease"]["pid"], owner_pid)
            self.assertFalse(blocked["lease"]["ownedByCurrentProcess"])
            self.assertFalse(blocked["lease"]["stale"])

            time.sleep(ttl_seconds + 0.4)

            takeover = self._run_global_lease_probe_process(ttl_seconds=ttl_seconds)
            self.assertTrue(takeover["acquired"])
            self.assertTrue(takeover["lease"]["ownedByCurrentProcess"])
            self.assertFalse(takeover["lease"]["stale"])
        finally:
            self._cleanup_global_lease_probe_process(owner, force_kill=True)

    def test_global_autodrive_watchdog_restarts_cancelled_supervisor(self):
        async def scenario():
            async def steady_continue_task(_service, *, task_id, create_plan_if_needed):
                return SimpleNamespace(
                    action="stop",
                    reason="no_high_value_action",
                    summary="当前没有更高价值的下一步。",
                    task=None,
                    scope_task_id=None,
                    run=None,
                    error=None,
                )

            with (
                patch.object(type(config.settings), "is_test_env", new_callable=PropertyMock, return_value=False),
                patch("services.task_autodrive.GLOBAL_AUTO_DRIVE_POLL_INTERVAL_SECONDS", new=0.05),
                patch("services.task_dispatcher.TaskDispatcherService.continue_task", new=steady_continue_task),
            ):
                service = GlobalAutoDriveService()
                await service.start()

                deadline = asyncio.get_running_loop().time() + 1.0
                original_task = None
                while asyncio.get_running_loop().time() < deadline:
                    original_task = _GLOBAL_STATE.task
                    if original_task is not None and not original_task.done():
                        break
                    await asyncio.sleep(0.05)
                else:
                    self.fail("global autodrive did not start a production supervisor task")

                original_task.cancel()

                deadline = asyncio.get_running_loop().time() + 1.0
                restarted_task = None
                while asyncio.get_running_loop().time() < deadline:
                    restarted_task = _GLOBAL_STATE.task
                    if restarted_task is not None and restarted_task is not original_task and not restarted_task.done():
                        break
                    await asyncio.sleep(0.05)
                else:
                    self.fail("global autodrive watchdog did not restart the cancelled supervisor")

                status = await service.get_status()
                self.assertTrue(status.enabled)
                self.assertTrue(status.running)
                self.assertIn(status.last_reason, {"global_auto_drive_restarting", "no_high_value_action"})

                stop_result = await service.stop()
                self.assertFalse(stop_result.enabled)

        asyncio.run(scenario())

    def test_global_autodrive_recent_events_stay_bounded_under_repeated_cycles(self):
        async def scenario():
            attempts = 0

            async def alternating_continue_task(_service, *, task_id, create_plan_if_needed):
                nonlocal attempts
                attempts += 1
                if attempts % 2 == 1:
                    raise RuntimeError(f"dispatcher boom {attempts}")
                return SimpleNamespace(
                    action="stop",
                    reason="no_high_value_action",
                    summary=f"cycle {attempts}",
                    task=None,
                    scope_task_id=None,
                    run=None,
                    error=None,
                )

            with (
                patch.object(type(config.settings), "is_test_env", new_callable=PropertyMock, return_value=False),
                patch("services.task_autodrive.GLOBAL_AUTO_DRIVE_POLL_INTERVAL_SECONDS", new=0.01),
                patch("services.task_dispatcher.TaskDispatcherService.continue_task", new=alternating_continue_task),
            ):
                service = GlobalAutoDriveService()
                start_result = await service.start()
                self.assertTrue(start_result.enabled)

                deadline = asyncio.get_running_loop().time() + 0.45
                while asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(0.02)

                status = await service.get_status()
                self.assertTrue(status.enabled)
                self.assertGreaterEqual(attempts, 8)
                self.assertLessEqual(len(status.recent_events), 12)
                self.assertTrue(any(item["reason"] == "global_auto_drive_error" for item in status.recent_events))
                self.assertTrue(any(item["reason"] == "no_high_value_action" for item in status.recent_events))

                stop_result = await service.stop()
                self.assertFalse(stop_result.enabled)

        asyncio.run(scenario())

    def test_startup_marks_inflight_runs_as_failed(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "重启后收口 in-flight run",
                "repoPath": "D:/Repos/KAM",
                "status": "in_progress",
                "priority": "high",
            },
        ).json()
        asyncio.run(self._seed_running_run(task["id"]))

        self._restart_client(clear_persistence=True)

        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(len(detail["runs"]), 1)
        self.assertEqual(detail["runs"][0]["status"], "failed")
        self.assertEqual(detail["runs"][0]["resultSummary"], "执行中断：服务重启前的 run 未完成，已标记为 failed。")
        self.assertIn("Harness run interrupted before completion", detail["runs"][0]["rawOutput"])

    def test_dispatch_next_tries_later_parent_when_first_parent_has_no_new_follow_up(self):
        asyncio.run(self._seed_parent_selection_gap())

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：later parent dispatch"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": True})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "planned_task")
        self.assertEqual(payload["plannedFromTaskId"], "taskroot0002")
        self.assertEqual(payload["task"]["metadata"]["parentTaskId"], "taskroot0002")
        self.assertEqual(payload["run"]["status"], "passed")

    def test_manual_run_prefers_global_autodrive_scheduler_when_enabled(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "run 完成后优先续全局",
                "repoPath": "D:/Repos/KAM",
                "status": "in_progress",
                "priority": "high",
            },
        ).json()
        schedule_calls: list[str] = []

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：prefer global scheduler"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        async def fake_schedule_global_autodrive_if_enabled():
            schedule_calls.append("global")
            return True

        async def fake_schedule_autodrive_for_task(task_id: str | None):
            schedule_calls.append(f"scope:{task_id}")
            return task_id

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
            patch("services.run_engine.schedule_global_autodrive_if_enabled", new=fake_schedule_global_autodrive_if_enabled),
            patch("services.run_engine.schedule_autodrive_for_task", new=fake_schedule_autodrive_for_task),
        ):
            response = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "codex", "task": "执行完成后应该优先回到全局调度。"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(schedule_calls, ["global"])

    def test_manual_run_does_not_autodrive_without_opt_in(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "单轮 run 不应自动扩散",
                "repoPath": "D:/Repos/KAM",
                "status": "in_progress",
                "priority": "high",
            },
        ).json()

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：single run"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            response = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "codex", "task": "只跑这一轮，不要自动继续"},
            )

        self.assertEqual(response.status_code, 200)
        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(len(detail["runs"]), 1)
        self.assertEqual(detail["runs"][0]["status"], "passed")
        self.assertNotIn("autoDriveEnabled", detail["metadata"])

    def test_create_task_run_rejects_when_dependencies_unresolved(self):
        prerequisite = self.client.post(
            "/api/tasks",
            json={"title": "前置任务", "repoPath": "D:/Repos/KAM", "status": "open", "priority": "high"},
        ).json()
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "依赖阻塞的任务",
                "repoPath": "D:/Repos/KAM",
                "status": "open",
                "priority": "medium",
                "dependsOnTaskIds": [prerequisite["id"]],
            },
        ).json()

        response = self.client.post(
            f"/api/tasks/{task['id']}/runs",
            json={"agent": "codex", "task": "不应该允许直接开跑。"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("依赖未完成", response.json()["detail"])

    def test_retry_run_rejects_when_dependencies_unresolved(self):
        asyncio.run(self._seed_retry_blocked_task())

        response = self.client.post("/api/runs/runblock001/retry")

        self.assertEqual(response.status_code, 409)
        self.assertIn("依赖未完成", response.json()["detail"])

    def test_task_family_autodrive_records_dispatch_timeout(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})

        async def slow_continue_task(_service, *, task_id, create_plan_if_needed):
            await asyncio.sleep(0.15)
            return SimpleNamespace(
                action="stop",
                reason="no_high_value_action",
                summary="不应该走到这里。",
                task=None,
                scope_task_id=task_id,
                run=None,
                error=None,
            )

        with (
            patch("services.task_autodrive.AUTO_DRIVE_DECISION_TIMEOUT_SECONDS", new=0.05),
            patch("services.task_dispatcher.TaskDispatcherService.continue_task", new=slow_continue_task),
        ):
            response = self.client.post("/api/tasks/task-harness-cutover/autodrive/start")

        self.assertEqual(response.status_code, 200)
        detail = self.client.get("/api/tasks/task-harness-cutover").json()
        self.assertTrue(detail["metadata"]["autoDriveEnabled"])
        self.assertEqual(detail["metadata"]["autoDriveStatus"], "error")
        self.assertEqual(detail["metadata"]["autoDriveLastAction"], "stop")
        self.assertEqual(detail["metadata"]["autoDriveLastReason"], "auto_drive_dispatch_timeout")
        self.assertIn("单步调度超过 0.05s", detail["metadata"]["autoDriveLastSummary"])
        self.assertTrue(
            any(item["reason"] == "auto_drive_dispatch_timeout" for item in detail["metadata"]["autoDriveRecentEvents"])
        )

    def test_autodrive_stop_disables_scope_metadata(self):
        self.client.post("/api/dev/seed-harness", json={"reset": True})

        response = self.client.post("/api/tasks/task-harness-cutover/autodrive/stop")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scopeTaskId"], "task-harness-cutover")
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["running"])
        self.assertIn("已停止当前任务族的自动托管", payload["summary"])

        detail = self.client.get("/api/tasks/task-harness-cutover").json()
        self.assertFalse(detail["metadata"]["autoDriveEnabled"])
        self.assertEqual(detail["metadata"]["autoDriveStatus"], "disabled")
        self.assertEqual(detail["metadata"]["autoDriveLastSummary"], "已停止当前任务族的自动托管。")

    def test_startup_applies_alembic_head(self):
        version = asyncio.run(self._get_alembic_version())
        self.assertEqual(version, self._get_alembic_head())

    def test_claude_command_uses_noninteractive_print_mode(self):
        command = RunEngine(None)._build_command("claude-code", "打印 smoke 标记", Path("D:/tmp"))
        self.assertEqual(Path(command[0]).name.lower(), "claude.cmd")
        self.assertEqual(
            command[1:5],
            ["-p", "--dangerously-skip-permissions", "--output-format", "text"],
        )

    def test_archived_task_is_hidden_from_default_list(self):
        task = self.client.post("/api/tasks", json={"title": "过渡任务"}).json()
        archived = self.client.post(f"/api/tasks/{task['id']}/archive").json()
        self.assertEqual(archived["status"], "archived")

        tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(tasks, [])

        archived_tasks = self.client.get("/api/tasks?include_archived=true").json()["tasks"]
        self.assertEqual(len(archived_tasks), 1)

    def test_missing_harness_resources_return_404(self):
        task_response = self.client.get("/api/tasks/missing-task")
        snapshot_response = self.client.get("/api/context/snapshots/missing-snapshot")
        artifact_response = self.client.get("/api/runs/missing-run/artifacts")

        self.assertEqual(task_response.status_code, 404)
        self.assertEqual(task_response.json()["detail"], "任务不存在")
        self.assertEqual(snapshot_response.status_code, 404)
        self.assertEqual(snapshot_response.json()["detail"], "上下文快照不存在")
        self.assertEqual(artifact_response.status_code, 404)
        self.assertEqual(artifact_response.json()["detail"], "执行记录不存在")

    def test_legacy_v3_surface_is_removed(self):
        projects_response = self.client.post("/api/projects", json={"title": "旧项目"})
        threads_response = self.client.get("/api/threads/legacy-thread")
        seed_demo_response = self.client.post("/api/dev/seed-demo", json={"reset": True})

        self.assertEqual(projects_response.status_code, 405)
        self.assertEqual(projects_response.json()["detail"], "Method Not Allowed")
        self.assertEqual(threads_response.status_code, 404)
        self.assertEqual(threads_response.json()["detail"], "未找到页面")
        self.assertEqual(seed_demo_response.status_code, 405)
        self.assertEqual(seed_demo_response.json()["detail"], "Method Not Allowed")

    def test_operator_control_plane_reports_focus_and_actions(self):
        payload = self.client.post("/api/dev/seed-harness", json={"reset": True}).json()
        response = self.client.get(f"/api/operator/control-plane?task_id={payload['taskId']}")

        self.assertEqual(response.status_code, 200)
        control_plane = response.json()
        action_keys = {item["key"] for item in control_plane["actions"]}

        self.assertEqual(control_plane["focus"]["task"]["id"], payload["taskId"])
        self.assertEqual(control_plane["focus"]["scopeTask"]["id"], payload["taskId"])
        self.assertIn("当前焦点任务", control_plane["systemSummary"])
        self.assertGreaterEqual(control_plane["stats"]["totalTaskCount"], 1)
        self.assertEqual(control_plane["stats"]["scopeAutodriveEnabledCount"], 0)
        self.assertTrue({"start_global_autodrive", "dispatch_next", "continue_task_family", "start_task_autodrive"}.issubset(action_keys))

    def test_operator_actions_can_restart_global_autodrive(self):
        async def idle_continue_task(_service, *, task_id, create_plan_if_needed):
            return SimpleNamespace(
                action="stop",
                reason="no_high_value_action",
                summary="当前没有更高价值的自动下一步。",
                task=None,
                scope_task_id=None,
                run=None,
                error=None,
            )

        with (
            patch.object(type(config.settings), "is_test_env", new_callable=PropertyMock, return_value=False),
            patch("services.task_autodrive.GLOBAL_AUTO_DRIVE_POLL_INTERVAL_SECONDS", new=0.05),
            patch("services.task_dispatcher.TaskDispatcherService.continue_task", new=idle_continue_task),
        ):
            started = self.client.post("/api/operator/actions", json={"action": "start_global_autodrive"})
            self.assertEqual(started.status_code, 200)
            self.assertTrue(started.json()["controlPlane"]["globalAutoDrive"]["enabled"])

            restarted = self.client.post("/api/operator/actions", json={"action": "restart_global_autodrive"})
            self.assertEqual(restarted.status_code, 200)
            restarted_payload = restarted.json()
            self.assertEqual(restarted_payload["action"], "restart_global_autodrive")
            self.assertTrue(restarted_payload["controlPlane"]["globalAutoDrive"]["enabled"])
            self.assertIn("重启全局无人值守", restarted_payload["summary"])

            stopped = self.client.post("/api/operator/actions", json={"action": "stop_global_autodrive"})
            self.assertEqual(stopped.status_code, 200)
            self.assertFalse(stopped.json()["controlPlane"]["globalAutoDrive"]["enabled"])

    def test_operator_action_can_cancel_running_run(self):
        async def slow_run_command(_engine, command, cwd):
            await asyncio.sleep(10)
            return 0, "should not finish"

        with (
            patch.object(type(config.settings), "is_test_env", new_callable=PropertyMock, return_value=False),
            patch("services.run_engine.RunEngine._run_command", new=slow_run_command),
        ):
            task = self.client.post(
                "/api/tasks",
                json={
                    "title": "打断当前运行中的 run",
                    "status": "in_progress",
                    "priority": "high",
                    "labels": ["dogfood", "operator"],
                    "metadata": {
                        "recommendedPrompt": "执行一个很慢的 run。",
                        "recommendedAgent": "codex",
                    },
                },
            ).json()

            run = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "codex", "task": "执行一个很慢的 run。"},
            ).json()

            deadline = time.time() + 2.0
            while time.time() < deadline:
                current = self.client.get(f"/api/runs/{run['id']}").json()
                if current["status"] == "running":
                    break
                time.sleep(0.05)
            else:
                self.fail("run did not enter running state before cancel")

            control_plane = self.client.get(f"/api/operator/control-plane?task_id={task['id']}").json()
            cancel_action = next((item for item in control_plane["actions"] if item["key"] == "cancel_run"), None)
            self.assertIsNotNone(cancel_action)
            self.assertEqual(cancel_action["runId"], run["id"])

            cancelled = self.client.post(
                "/api/operator/actions",
                json={"action": "cancel_run", "taskId": task["id"], "runId": run["id"]},
            )
            self.assertEqual(cancelled.status_code, 200)
            cancelled_payload = cancelled.json()
            self.assertEqual(cancelled_payload["runId"], run["id"])
            self.assertIn("已打断 run", cancelled_payload["summary"])

            refreshed = self.client.get(f"/api/runs/{run['id']}").json()
            self.assertEqual(refreshed["status"], "cancelled")
            self.assertIn("执行已取消", refreshed["resultSummary"])

    async def _truncate_tables(self):
        async with engine.begin() as conn:
            for table in (
                "review_compares",
                "task_run_artifacts",
                "task_runs",
                "context_snapshots",
                "task_refs",
                "tasks",
            ):
                await conn.execute(text(f'DELETE FROM "{table}"'))

    async def _get_alembic_version(self):
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one()

    def _get_alembic_head(self):
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        return ScriptDirectory.from_config(config).get_current_head()

    def _create_git_repo(self) -> Path:
        repo = TMP_ROOT / f"repo-{next(tempfile._get_candidate_names())}"
        repo.mkdir(parents=True)
        self._git(repo, "init")
        self._git(repo, "config", "user.name", "Test User")
        self._git(repo, "config", "user.email", "test@example.com")
        (repo / "README.md").write_text("before\n", encoding="utf-8")
        self._git(repo, "add", "README.md")
        self._git(repo, "commit", "-m", "Initial commit")
        return repo

    def _create_remote_backed_git_repo(self) -> tuple[Path, Path, str]:
        remote = TMP_ROOT / f"remote-{next(tempfile._get_candidate_names())}.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        repo = TMP_ROOT / f"repo-{next(tempfile._get_candidate_names())}"
        subprocess.run(
            ["git", "clone", str(remote), str(repo)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._git(repo, "config", "user.name", "Test User")
        self._git(repo, "config", "user.email", "test@example.com")
        (repo / "README.md").write_text("before remote push\n", encoding="utf-8")
        self._git(repo, "add", "README.md")
        self._git(repo, "commit", "-m", "Initial commit")
        self._git(repo, "branch", "-M", "main")
        self._git(repo, "push", "-u", "origin", "main")

        branch_name = "feature/pr-4518"
        self._git(repo, "checkout", "-b", branch_name)
        self._git(repo, "push", "-u", "origin", branch_name)
        self._git(repo, "checkout", "main")
        return repo, remote, branch_name

    def _git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _git_output(self, cwd: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout

    def _restart_client(self, *, clear_persistence: bool) -> None:
        self.client.__exit__(None, None, None)
        asyncio.run(engine.dispose())
        reset_autodrive_runtime_state(clear_persistence=clear_persistence)
        self.client = TestClient(app)
        self.client.__enter__()

    def _write_persisted_global_autodrive_state(self) -> None:
        state_path = TMP_ROOT / GLOBAL_AUTO_DRIVE_STATE_FILENAME
        state_path.write_text(
            json.dumps({"enabled": True, "updatedAt": datetime.now(UTC).isoformat()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_foreign_global_lease(self, *, stale: bool | None = None, age_seconds: float | None = None) -> None:
        lease_path = TMP_ROOT / GLOBAL_AUTO_DRIVE_LEASE_FILENAME
        if age_seconds is None:
            age_seconds = 30.0 if stale else 1.0
        heartbeat_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
        payload = {
            "ownerId": "foreign-host:4321:foreign",
            "pid": 4321,
            "hostname": "foreign-host",
            "acquiredAt": heartbeat_at.isoformat(),
            "heartbeatAt": heartbeat_at.isoformat(),
        }
        lease_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_global_lease_payload(self) -> dict[str, object] | None:
        lease_path = TMP_ROOT / GLOBAL_AUTO_DRIVE_LEASE_FILENAME
        if not lease_path.exists():
            return None
        return json.loads(lease_path.read_text(encoding="utf-8"))

    def _spawn_global_lease_probe_process(
        self,
        *,
        sleep_seconds: float,
        release_on_exit: bool,
        ttl_seconds: float | None = None,
    ) -> subprocess.Popen[str]:
        env = self._global_lease_probe_env(
            sleep_seconds=sleep_seconds,
            release_on_exit=release_on_exit,
            ttl_seconds=ttl_seconds,
        )
        return subprocess.Popen(
            [sys.executable, "-u", "-c", self._global_lease_probe_script()],
            cwd=str(BACKEND_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    def _run_global_lease_probe_process(self, *, ttl_seconds: float | None = None) -> dict[str, object]:
        env = self._global_lease_probe_env(
            sleep_seconds=0.0,
            release_on_exit=False,
            ttl_seconds=ttl_seconds,
        )
        completed = subprocess.run(
            [sys.executable, "-u", "-c", self._global_lease_probe_script()],
            cwd=str(BACKEND_ROOT),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        return json.loads(completed.stdout.strip())

    def _read_global_lease_probe_result(self, process: subprocess.Popen[str]) -> dict[str, object]:
        assert process.stdout is not None
        line = process.stdout.readline().strip()
        if not line:
            stderr = process.stderr.read().strip() if process.stderr is not None else ""
            self.fail(f"lease probe produced no stdout: {stderr}")
        return json.loads(line)

    def _cleanup_global_lease_probe_process(self, process: subprocess.Popen[str], *, force_kill: bool) -> None:
        if process.poll() is None:
            if force_kill:
                process.kill()
            else:
                process.terminate()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    def _global_lease_probe_env(
        self,
        *,
        sleep_seconds: float,
        release_on_exit: bool,
        ttl_seconds: float | None,
    ) -> dict[str, str]:
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP_ROOT / 'kam-harness.db').as_posix()}"
        env["STORAGE_PATH"] = str(TMP_ROOT)
        env["RUN_ROOT"] = str(TMP_ROOT / "runs")
        env["APP_ENV"] = "test"
        env["KAM_TEST_LEASE_SLEEP"] = str(sleep_seconds)
        env["KAM_TEST_LEASE_RELEASE"] = "1" if release_on_exit else "0"
        if ttl_seconds is not None:
            env["KAM_TEST_LEASE_TTL"] = str(ttl_seconds)
        return env

    def _global_lease_probe_script(self) -> str:
        return textwrap.dedent(
            f"""
            import json
            import os
            import sys
            import time
            from pathlib import Path

            backend_root = Path(r\"{BACKEND_ROOT}\")
            if str(backend_root) not in sys.path:
                sys.path.insert(0, str(backend_root))

            import services.task_autodrive as task_autodrive

            ttl_override = os.environ.get("KAM_TEST_LEASE_TTL")
            if ttl_override:
                task_autodrive.GLOBAL_AUTO_DRIVE_LEASE_TTL_SECONDS = float(ttl_override)

            acquired, _payload = task_autodrive._acquire_or_refresh_global_lease()
            print(json.dumps({{"acquired": acquired, "lease": task_autodrive._read_global_lease_status()}}, ensure_ascii=False), flush=True)

            sleep_seconds = float(os.environ.get("KAM_TEST_LEASE_SLEEP", "0"))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

            if os.environ.get("KAM_TEST_LEASE_RELEASE") == "1":
                task_autodrive._release_global_lease_if_owned()
            """
        )

    async def _seed_retryable_child_task(self) -> tuple[str, str]:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskparent01",
                    title="让 KAM 自动继续推进",
                    description="父任务等待子任务修复失败。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="high",
                    labels=["dogfood", "parent"],
                )
            )
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskchild001",
                    title="修复失败 child task",
                    description="优先重试失败子任务。",
                    repo_path=None,
                    status="in_progress",
                    priority="high",
                    labels=["dogfood", "child"],
                    metadata={
                        "parentTaskId": "taskparent01",
                        "sourceTaskId": "taskparent01",
                        "planningReason": "failed_run_follow_up",
                        "recommendedPrompt": "修复失败 child task 并重新验证。",
                        "recommendedAgent": "codex",
                        "acceptanceChecks": ["修复失败", "重新验证"],
                        "suggestedRefs": [],
                    },
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snapchild001",
                    task_id="taskchild001",
                    summary="Child retry snapshot",
                    content="## Task\n标题：修复失败 child task",
                    focus="先重试失败 run。",
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runchild001",
                    task_id="taskchild001",
                    agent="codex",
                    status="failed",
                    task="修复失败 child task 并重新验证。",
                    result_summary="执行失败：AssertionError: retry me",
                    changed_files=["backend/services/task_dispatcher.py"],
                    check_passed=False,
                    raw_output="AssertionError: retry me",
                )
            )
        return "taskparent01", "taskchild001"

    async def _seed_terminal_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskdone0001",
                    title="已经收口的任务",
                    description="不应该继续推进。",
                    repo_path="D:/Repos/KAM",
                    status="verified",
                    priority="medium",
                    labels=["done"],
                )
            )
        return "taskdone0001"

    async def _seed_running_run(self, task_id: str) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runactive001",
                    task_id=task_id,
                    agent="codex",
                    status="running",
                    task="继续执行中",
                    raw_output="still running",
                )
            )

    async def _seed_retry_blocked_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskdep001",
                    title="前置任务",
                    description="先完成这个前置任务。",
                    repo_path="D:/Repos/KAM",
                    status="open",
                    priority="high",
                    labels=["dogfood", "dependency"],
                )
            )
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskblock01",
                    title="被依赖阻塞的失败任务",
                    description="依赖未完成时不应允许 retry。",
                    repo_path="D:/Repos/KAM",
                    status="failed",
                    priority="high",
                    labels=["dogfood", "dependency"],
                    metadata={"dependsOnTaskIds": ["taskdep001"]},
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runblock001",
                    task_id="taskblock01",
                    agent="codex",
                    status="failed",
                    task="先修复依赖阻塞任务。",
                    result_summary="执行失败：AssertionError: blocked retry",
                    changed_files=["backend/services/task_dispatcher.py"],
                    check_passed=False,
                    raw_output="AssertionError: blocked retry",
                )
            )
        return "taskblock01"

    async def _seed_retryable_root_task(self, task_id: str) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.update()
                .where(Task.__table__.c.id == task_id)
                .values(
                    metadata={
                        "recommendedPrompt": "重试当前失败任务并重新验证。",
                        "recommendedAgent": "codex",
                        "acceptanceChecks": ["修复失败", "重新验证"],
                        "suggestedRefs": [],
                    }
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snaproot001",
                    task_id=task_id,
                    summary="Root retry snapshot",
                    content="## Task\n标题：直接重试当前失败任务",
                    focus="先重试当前失败 run。",
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runroot001",
                    task_id=task_id,
                    agent="codex",
                    status="failed",
                    task="重试当前失败任务并重新验证。",
                    result_summary="执行失败：AssertionError: retry root",
                    changed_files=["backend/services/task_dispatcher.py"],
                    check_passed=False,
                    raw_output="AssertionError: retry root",
                )
            )

    async def _seed_retry_exhausted_root_task(self, task_id: str) -> None:
        base = datetime.now(UTC)
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.update()
                .where(Task.__table__.c.id == task_id)
                .values(
                    metadata={
                        "recommendedPrompt": "重试当前失败任务并重新验证。",
                        "recommendedAgent": "codex",
                        "acceptanceChecks": ["修复失败", "重新验证"],
                        "suggestedRefs": [],
                    }
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snaprootx01",
                    task_id=task_id,
                    summary="Retry budget exhausted snapshot",
                    content="## Task\n标题：失败预算耗尽后停止自动继续",
                    focus="不要继续无上限重跑失败任务。",
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    [
                        {
                            "id": "runrootx001",
                            "task_id": task_id,
                            "agent": "codex",
                            "status": "failed",
                            "task": "第一次失败，允许自动重试。",
                            "result_summary": "执行失败：AssertionError: retry budget 1",
                            "changed_files": ["backend/services/task_dispatcher.py"],
                            "check_passed": False,
                            "raw_output": "AssertionError: retry budget 1",
                            "created_at": base - timedelta(seconds=2),
                        },
                        {
                            "id": "runrootx002",
                            "task_id": task_id,
                            "agent": "codex",
                            "status": "failed",
                            "task": "第二次失败，应该触发自动停止。",
                            "result_summary": "执行失败：AssertionError: retry budget 2",
                            "changed_files": ["backend/services/task_dispatcher.py"],
                            "check_passed": False,
                            "raw_output": "AssertionError: retry budget 2",
                            "created_at": base - timedelta(seconds=1),
                        },
                    ]
                )
            )

    async def _seed_secondary_root_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskroot0002",
                    title="推进第二个 task family",
                    description="验证全局无人值守会继续跨 family 接活。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="medium",
                    labels=["dogfood", "global"],
                )
            )
        return "taskroot0002"

    async def _seed_failed_root_with_generic_child(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskrootfg01",
                    title="优先处理 root 失败任务",
                    description="failed root 不应被 generic child 抢跑。",
                    repo_path="D:/Repos/KAM",
                    status="failed",
                    priority="high",
                    labels=["dogfood", "dispatcher"],
                    metadata={
                        "recommendedPrompt": "先修复当前 root 失败任务并重新验证。",
                        "recommendedAgent": "codex",
                        "acceptanceChecks": ["修复失败", "重新验证"],
                        "suggestedRefs": [],
                    },
                )
            )
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskchildfg1",
                    title="generic child follow-up",
                    description="这张 child 不应抢在 failed root 前面。",
                    repo_path="D:/Repos/KAM",
                    status="open",
                    priority="high",
                    labels=["dogfood", "dispatcher"],
                    metadata={
                        "parentTaskId": "taskrootfg01",
                        "sourceTaskId": "taskrootfg01",
                        "planningReason": "task_next_step",
                        "recommendedPrompt": "继续推进 generic child follow-up。",
                        "recommendedAgent": "codex",
                        "acceptanceChecks": ["继续推进"],
                        "suggestedRefs": [],
                    },
                )
            )
        return "taskrootfg01"

    async def _seed_retryable_child_for_parent(self, parent_task_id: str) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskadptc001",
                    title="等待后续修复的 child task",
                    description="这里有失败 run，但继续时应该先 adopt 已通过结果。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="high",
                    labels=["dogfood", "child"],
                    metadata={
                        "parentTaskId": parent_task_id,
                        "sourceTaskId": parent_task_id,
                        "planningReason": "failed_run_follow_up",
                        "recommendedPrompt": "修复失败 child task 并重新验证。",
                        "recommendedAgent": "codex",
                        "acceptanceChecks": ["修复失败", "重新验证"],
                        "suggestedRefs": [],
                    },
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snapadptc01",
                    task_id="taskadptc001",
                    summary="Child retry snapshot",
                    content="## Task\n标题：等待后续修复的 child task",
                    focus="这里本来可以 retry，但应先 adopt 已通过结果。",
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runadptc001",
                    task_id="taskadptc001",
                    agent="codex",
                    status="failed",
                    task="修复失败 child task 并重新验证。",
                    result_summary="执行失败：AssertionError: retry me later",
                    changed_files=["backend/services/task_dispatcher.py"],
                    check_passed=False,
                    raw_output="AssertionError: retry me later",
                )
            )
        return "taskadptc001"

    async def _seed_parent_selection_gap(self) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskroot0001",
                    title="第一个 root 已无新 follow-up",
                    description="planner 不应卡死在这里。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="high",
                    labels=["dogfood", "planner"],
                )
            )
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskroot0002",
                    title="第二个 root 仍可继续推进",
                    description="planner 应该继续尝试后面的 root。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="medium",
                    labels=["dogfood", "planner"],
                )
            )
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskrootdone1",
                    title="已存在的 generic follow-up",
                    description="用于挡住第一个 root 的 generic 下一步。",
                    repo_path="D:/Repos/KAM",
                    status="verified",
                    priority="medium",
                    labels=["dogfood", "planner"],
                    metadata={
                        "parentTaskId": "taskroot0001",
                        "sourceTaskId": "taskroot0001",
                        "sourceKind": "task",
                        "planningReason": "task_next_step",
                        "recommendedPrompt": "这个 child 已经存在。",
                        "recommendedAgent": "codex",
                        "acceptanceChecks": ["noop"],
                        "suggestedRefs": [],
                    },
                )
            )
