from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sse_starlette.sse import AppStatus
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

from db import engine  # noqa: E402
from main import app  # noqa: E402
from services.run_engine import wait_for_background_runs  # noqa: E402


class HarnessApiTests(unittest.TestCase):
    def setUp(self):
        AppStatus.should_exit_event = asyncio.Event()
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(self._truncate_tables())

    def tearDown(self):
        asyncio.run(wait_for_background_runs())
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

        async def fake_run_command(_engine, run, _command, _cwd):
            return 0, f"执行完成：{run.task}"

        async def fake_prepare_execution(_engine, _run, _project):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_execution", new=fake_prepare_execution),
        ):
            run_one = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "codex", "task": "先建立 Task 和 Snapshot API"},
            ).json()
            run_two = self.client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agent": "claude-code", "task": "补 Compare 和 Artifacts API"},
            ).json()

        self.assertEqual(run_one["status"], "passed")
        self.assertEqual(run_two["status"], "passed")

        detail = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(len(detail["refs"]), 1)
        self.assertEqual(len(detail["snapshots"]), 1)
        self.assertEqual(len(detail["runs"]), 2)

        artifacts = self.client.get(f"/api/runs/{run_one['id']}/artifacts").json()["artifacts"]
        artifact_types = {artifact["type"] for artifact in artifacts}
        self.assertTrue({"task_snapshot", "context_snapshot", "task", "stdout", "summary"}.issubset(artifact_types))

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

        artifacts = self.client.get("/api/runs/task-run-2/artifacts").json()["artifacts"]
        self.assertTrue(any(item["type"] == "stdout" for item in artifacts))

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

    def test_legacy_v3_routes_are_disabled_by_default(self):
        projects_response = self.client.post("/api/projects", json={"title": "旧项目"})
        threads_response = self.client.get("/api/threads/legacy-thread")

        self.assertEqual(projects_response.status_code, 405)
        self.assertEqual(projects_response.json()["detail"], "Method Not Allowed")
        self.assertEqual(threads_response.status_code, 404)
        self.assertEqual(threads_response.json()["detail"], "未找到页面")

    async def _truncate_tables(self):
        async with engine.begin() as conn:
            for table in (
                "review_compares",
                "run_artifacts",
                "context_snapshots",
                "task_refs",
                "tasks",
                "watcher_events",
                "watchers",
                "memories",
                "runs",
                "messages",
                "threads",
                "projects",
            ):
                await conn.execute(text(f'DELETE FROM "{table}"'))
