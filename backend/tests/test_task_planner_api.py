from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text


TMP_ROOT = Path(tempfile.mkdtemp(prefix="kam-task-planner-tests-"))
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP_ROOT / 'kam-task-planner.db').as_posix()}"
os.environ["STORAGE_PATH"] = str(TMP_ROOT)
os.environ["RUN_ROOT"] = str(TMP_ROOT / "runs")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["APP_ENV"] = "test"

from db import engine  # noqa: E402
from main import app  # noqa: E402
from models import ReviewCompare, Task, TaskRun  # noqa: E402


class TaskPlannerApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(self._truncate_tables())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        asyncio.run(engine.dispose())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_plan_creates_follow_up_tasks_from_run_and_compare(self):
        task_id = asyncio.run(self._seed_parent_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 3})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["taskId"], task_id)
        self.assertGreaterEqual(len(payload["suggestions"]), 2)
        self.assertEqual(len(payload["tasks"]), len(payload["suggestions"]))
        planning_reasons = {item["metadata"]["planningReason"] for item in payload["tasks"]}
        self.assertIn("passed_run_not_adopted", planning_reasons)
        self.assertIn("review_compare_follow_up", planning_reasons)
        self.assertTrue(all(item["metadata"]["parentTaskId"] == task_id for item in payload["tasks"]))
        self.assertTrue(all(item["metadata"]["sourceTaskId"] == task_id for item in payload["tasks"]))
        self.assertTrue(all(item["metadata"]["sourceKind"] in {"run", "compare"} for item in payload["tasks"]))

        all_tasks = self.client.get("/api/tasks").json()["tasks"]
        follow_up_titles = {item["title"] for item in all_tasks}
        self.assertTrue(any(title.startswith("采纳并验证：") for title in follow_up_titles))
        self.assertTrue(any(title.startswith("根据 compare 推进：") for title in follow_up_titles))

    def test_plan_skips_duplicate_follow_up_tasks(self):
        task_id = asyncio.run(self._seed_parent_task())

        first = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 3}).json()
        second = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 3}).json()

        self.assertGreaterEqual(len(first["tasks"]), 2)
        self.assertEqual(second["suggestions"], [])
        self.assertEqual(second["tasks"], [])

    def test_plan_can_return_suggestions_without_creating_tasks(self):
        task_id = asyncio.run(self._seed_parent_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": False, "limit": 2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["taskId"], task_id)
        self.assertEqual(payload["tasks"], [])
        self.assertEqual(len(payload["suggestions"]), 2)
        self.assertTrue(all(item["metadata"]["parentTaskId"] == task_id for item in payload["suggestions"]))
        self.assertTrue(all(item["metadata"]["sourceTaskId"] == task_id for item in payload["suggestions"]))

        all_tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(all_tasks), 1)
        self.assertEqual(all_tasks[0]["id"], task_id)

    async def _seed_parent_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskplan1234",
                    title="让 KAM 自己给自己排工作",
                    description="基于当前上下文自动拆后续任务。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="high",
                    labels=["dogfood", "planner"],
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runplan1234",
                    task_id="taskplan1234",
                    agent="codex",
                    status="passed",
                    task="把当前任务拆成下一轮可以继续做的工作单元",
                    result_summary="已经有可采纳的实现和后续差异。",
                    changed_files=["backend/api/tasks.py", "app/src/App.tsx"],
                    check_passed=True,
                    raw_output="ok",
                )
            )
            await conn.execute(
                ReviewCompare.__table__.insert().values(
                    id="cmpplan1234",
                    task_id="taskplan1234",
                    title="自排工作 compare",
                    run_ids=["runplan1234", "other-run"],
                    summary="对比 2 个 run：一条已经产出实现，另一条说明还要补任务拆分和收口。",
                )
            )
        return "taskplan1234"

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
