from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

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
from models import ContextSnapshot, ReviewCompare, Task, TaskRef, TaskRun, TaskRunArtifact  # noqa: E402


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

    def test_plan_creates_follow_up_tasks_with_execution_metadata_and_refs(self):
        task_id = asyncio.run(self._seed_adopt_and_compare_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 3})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["taskId"], task_id)
        self.assertGreaterEqual(len(payload["suggestions"]), 2)
        self.assertEqual(len(payload["tasks"]), len(payload["suggestions"]))

        planning_reasons = {item["metadata"]["planningReason"] for item in payload["tasks"]}
        self.assertIn("passed_run_not_adopted", planning_reasons)
        self.assertIn("review_compare_follow_up", planning_reasons)

        adopt_task = next(item for item in payload["tasks"] if item["metadata"]["planningReason"] == "passed_run_not_adopted")
        self.assertEqual(adopt_task["metadata"]["recommendedAgent"], "codex")
        self.assertTrue(adopt_task["metadata"]["recommendedPrompt"].startswith("收口父任务"))
        self.assertGreaterEqual(len(adopt_task["metadata"]["acceptanceChecks"]), 3)
        self.assertGreaterEqual(len(adopt_task["metadata"]["suggestedRefs"]), 3)

        adopt_detail = self.client.get(f"/api/tasks/{adopt_task['id']}").json()
        ref_values = {item["value"] for item in adopt_detail["refs"]}
        ref_kinds = {item["kind"] for item in adopt_detail["refs"]}
        self.assertIn("backend/api/tasks.py", ref_values)
        self.assertIn("snapshot", ref_kinds)
        self.assertIn("run", ref_kinds)

    def test_plan_skips_duplicate_follow_up_tasks(self):
        task_id = asyncio.run(self._seed_adopt_and_compare_task())

        first = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 3}).json()
        second = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 3}).json()

        self.assertGreaterEqual(len(first["tasks"]), 2)
        self.assertEqual(second["suggestions"], [])
        self.assertEqual(second["tasks"], [])

    def test_plan_can_return_suggestions_without_creating_tasks(self):
        task_id = asyncio.run(self._seed_adopt_and_compare_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": False, "limit": 2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["taskId"], task_id)
        self.assertEqual(payload["tasks"], [])
        self.assertEqual(len(payload["suggestions"]), 2)
        self.assertTrue(all(item["metadata"]["parentTaskId"] == task_id for item in payload["suggestions"]))
        self.assertTrue(all(item["metadata"]["sourceTaskId"] == task_id for item in payload["suggestions"]))
        self.assertTrue(all(item["recommendedPrompt"] for item in payload["suggestions"]))
        self.assertTrue(all(item["recommendedAgent"] == "codex" for item in payload["suggestions"]))
        self.assertTrue(all(item["acceptanceChecks"] for item in payload["suggestions"]))
        self.assertTrue(all(item["suggestedRefs"] for item in payload["suggestions"]))

        all_tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(all_tasks), 1)
        self.assertEqual(all_tasks[0]["id"], task_id)

    def test_plan_prioritizes_failed_run_execution_context(self):
        task_id = asyncio.run(self._seed_failed_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": False, "limit": 2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(len(payload["suggestions"]), 1)
        suggestion = payload["suggestions"][0]
        self.assertEqual(suggestion["metadata"]["planningReason"], "failed_run_follow_up")
        self.assertTrue(suggestion["recommendedPrompt"].startswith("修复失败 run"))
        self.assertIn("backend/services/router.py", suggestion["recommendedPrompt"])
        self.assertGreaterEqual(len(suggestion["acceptanceChecks"]), 3)
        self.assertTrue(any(ref["value"] == "backend/services/router.py" for ref in suggestion["suggestedRefs"]))

    def test_plan_falls_back_to_generic_next_step_with_snapshot_and_refs(self):
        task_id = asyncio.run(self._seed_generic_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": False, "limit": 1})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(len(payload["suggestions"]), 1)
        suggestion = payload["suggestions"][0]
        self.assertEqual(suggestion["metadata"]["planningReason"], "task_next_step")
        self.assertTrue(suggestion["recommendedPrompt"].startswith("继续推进父任务"))
        self.assertTrue(any(ref["kind"] == "snapshot" for ref in suggestion["suggestedRefs"]))
        self.assertTrue(any(ref["value"] == "docs/product/ai_work_assistant_prd.md" for ref in suggestion["suggestedRefs"]))

    def test_plan_does_not_generate_adopt_follow_up_for_already_adopted_run(self):
        task_id = asyncio.run(self._seed_adopted_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": False, "limit": 2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        reasons = [item["metadata"]["planningReason"] for item in payload["suggestions"]]
        self.assertNotIn("passed_run_not_adopted", reasons)
        self.assertEqual(reasons, ["task_next_step"])

    def test_plan_does_not_generate_more_follow_ups_for_terminal_parent_task(self):
        task_id = asyncio.run(self._seed_terminal_task())

        response = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["suggestions"], [])
        self.assertEqual(payload["tasks"], [])

    def test_planned_child_task_can_start_run_with_generated_context(self):
        task_id = asyncio.run(self._seed_adopt_and_compare_task())

        planned = self.client.post(f"/api/tasks/{task_id}/plan", json={"createTasks": True, "limit": 1}).json()
        child_task = planned["tasks"][0]

        async def fake_run_command(_engine, _command, _cwd):
            return 0, "执行完成：planner child run"

        async def fake_prepare_task_execution(_engine, _run, _task):
            return None, ["fake-agent"]

        with (
            patch("services.run_engine.RunEngine._run_command", new=fake_run_command),
            patch("services.run_engine.RunEngine._prepare_task_execution", new=fake_prepare_task_execution),
        ):
            run = self.client.post(
                f"/api/tasks/{child_task['id']}/runs",
                json={"agent": "codex", "task": child_task["metadata"]["recommendedPrompt"]},
            )
        self.assertEqual(run.status_code, 200)
        payload = run.json()
        self.assertEqual(payload["status"], "passed")

        artifacts = self.client.get(f"/api/runs/{payload['id']}/artifacts").json()["artifacts"]
        artifact_types = {artifact["type"] for artifact in artifacts}
        self.assertTrue({"task_snapshot", "context_snapshot", "task", "stdout", "summary"}.issubset(artifact_types))

    async def _seed_adopt_and_compare_task(self) -> str:
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
                TaskRef.__table__.insert().values(
                    id="refplan1234",
                    task_id="taskplan1234",
                    kind="file",
                    label="Planner",
                    value="backend/services/task_planner.py",
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snapplan1234",
                    task_id="taskplan1234",
                    summary="自排工作 · 1 refs",
                    content="## Task\n标题：让 KAM 自己给自己排工作",
                    focus="先把 planner 拆出的任务变得可执行。",
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
                TaskRunArtifact.__table__.insert().values(
                    [
                        {
                            "id": "artplan001",
                            "task_run_id": "runplan1234",
                            "type": "summary",
                            "content": "已经有可采纳的实现和后续差异。",
                        },
                        {
                            "id": "artplan002",
                            "task_run_id": "runplan1234",
                            "type": "changed_files",
                            "content": '["backend/api/tasks.py","app/src/App.tsx"]',
                        },
                    ]
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

    async def _seed_failed_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskfail1234",
                    title="修复 planner 失败回归",
                    description="处理失败 run 并恢复主链路。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="high",
                    labels=["dogfood", "failure"],
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snapfail1234",
                    task_id="taskfail1234",
                    summary="失败修复 · 0 refs",
                    content="## Task\n标题：修复 planner 失败回归",
                    focus="先消除失败，再恢复默认门禁。",
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runfail1234",
                    task_id="taskfail1234",
                    agent="codex",
                    status="failed",
                    task="修复 task planner 的直接回归",
                    result_summary="执行失败：AssertionError: planner output mismatch",
                    changed_files=["backend/services/router.py"],
                    check_passed=False,
                    raw_output="Traceback\nAssertionError: planner output mismatch",
                )
            )
            await conn.execute(
                TaskRunArtifact.__table__.insert().values(
                    [
                        {
                            "id": "artfail001",
                            "task_run_id": "runfail1234",
                            "type": "summary",
                            "content": "执行失败：AssertionError: planner output mismatch",
                        },
                        {
                            "id": "artfail002",
                            "task_run_id": "runfail1234",
                            "type": "stdout",
                            "content": "AssertionError: planner output mismatch",
                        },
                    ]
                )
            )
        return "taskfail1234"

    async def _seed_generic_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="tasknext1234",
                    title="继续推进 dogfood planner",
                    description="当前没有 run 和 compare，先落下一步。",
                    repo_path="D:/Repos/KAM",
                    status="open",
                    priority="medium",
                    labels=["dogfood"],
                )
            )
            await conn.execute(
                TaskRef.__table__.insert().values(
                    id="refnext1234",
                    task_id="tasknext1234",
                    kind="file",
                    label="PRD",
                    value="docs/product/ai_work_assistant_prd.md",
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snapnext1234",
                    task_id="tasknext1234",
                    summary="Generic next step · 1 refs",
                    content="## Task\n标题：继续推进 dogfood planner",
                    focus="先形成下一轮可执行任务。",
                )
            )
        return "tasknext1234"

    async def _seed_adopted_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskadpt1234",
                    title="已采纳的任务",
                    description="通过 run 已经采纳，不应再产出 adopt follow-up。",
                    repo_path="D:/Repos/KAM",
                    status="in_progress",
                    priority="medium",
                    labels=["dogfood"],
                )
            )
            await conn.execute(
                ContextSnapshot.__table__.insert().values(
                    id="snapadpt1234",
                    task_id="taskadpt1234",
                    summary="Adopted snapshot",
                    content="## Task\n标题：已采纳的任务",
                    focus="验证 planner 不再建议 adopt。",
                )
            )
            await conn.execute(
                TaskRun.__table__.insert().values(
                    id="runadpt1234",
                    task_id="taskadpt1234",
                    agent="codex",
                    status="passed",
                    task="收口并采纳当前实现",
                    result_summary="已通过并采纳。",
                    changed_files=["backend/services/task_planner.py"],
                    check_passed=True,
                    raw_output="ok",
                    adopted_at=datetime(2026, 4, 5, 6, 30, tzinfo=UTC),
                )
            )
        return "taskadpt1234"

    async def _seed_terminal_task(self) -> str:
        async with engine.begin() as conn:
            await conn.execute(
                Task.__table__.insert().values(
                    id="taskterm1234",
                    title="已完成父任务",
                    description="terminal task 不应继续拆 follow-up。",
                    repo_path="D:/Repos/KAM",
                    status="verified",
                    priority="high",
                    labels=["done"],
                )
            )
        return "taskterm1234"

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
