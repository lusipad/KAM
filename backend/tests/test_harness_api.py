from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

from db import engine  # noqa: E402
from main import app  # noqa: E402
from models import ContextSnapshot, Task, TaskRun  # noqa: E402
from services.run_engine import RunEngine, wait_for_background_runs  # noqa: E402
from services.task_autodrive import reset_autodrive_runtime_state  # noqa: E402


class HarnessApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        reset_autodrive_runtime_state()
        asyncio.run(self._truncate_tables())

    def tearDown(self):
        asyncio.run(wait_for_background_runs())
        reset_autodrive_runtime_state()
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

    def test_dispatch_next_returns_conflict_when_no_task_available(self):
        response = self.client.post("/api/tasks/dispatch-next", json={"createPlanIfNeeded": False})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "当前没有可自动接手的任务")

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

        tasks = self.client.get("/api/tasks").json()["tasks"]
        child_tasks = [item for item in tasks if item["metadata"].get("parentTaskId") == "task-harness-cutover"]
        self.assertGreaterEqual(len(child_tasks), 2)
        self.assertTrue(all(item["status"] == "in_progress" for item in child_tasks))
        for item in child_tasks:
            detail = self.client.get(f"/api/tasks/{item['id']}").json()
            self.assertTrue(detail["runs"])
            self.assertEqual(detail["runs"][-1]["status"], "passed")

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

    def test_seed_harness_reset_clears_global_autodrive_runtime_state(self):
        self.client.post("/api/tasks/autodrive/global/start")

        response = self.client.post("/api/dev/seed-harness", json={"reset": True})

        self.assertEqual(response.status_code, 200)
        status = self.client.get("/api/tasks/autodrive/global").json()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["status"], "disabled")
        self.assertEqual(status["summary"], "当前还没有开启全局无人值守。")

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

        tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], task["id"])

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

    def _git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
