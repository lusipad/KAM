from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, PropertyMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text


TMP_ROOT = Path(tempfile.mkdtemp(prefix="kam-github-issue-monitors-tests-"))
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP_ROOT / 'kam-harness.db').as_posix()}"
os.environ["STORAGE_PATH"] = str(TMP_ROOT)
os.environ["RUN_ROOT"] = str(TMP_ROOT / "runs")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["APP_ENV"] = "test"

import config  # noqa: E402
from db import engine  # noqa: E402
from main import app  # noqa: E402
from services.github_issue_monitors import (  # noqa: E402
    recover_github_issue_monitor_runtime_state,
    reset_github_issue_monitor_runtime_state,
    shutdown_github_issue_monitor_runtime,
    upsert_issue_monitor,
)
from services.task_autodrive import reset_autodrive_runtime_state  # noqa: E402


class FakeControlResult:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, object]:
        return dict(self._payload)


class FakeAdapter:
    def __init__(self, current_state: dict, changes: dict, actions: list[dict]) -> None:
        self._current_state = current_state
        self._changes = changes
        self._actions = actions

    async def fetch(self, config: dict) -> dict:
        return self._current_state

    def diff(self, previous: dict | None, current: dict) -> dict:
        return self._changes

    def recommended_actions(self, watcher: dict, changes: dict) -> list[dict]:
        return self._actions


class GitHubIssueMonitorApiTests(unittest.TestCase):
    def setUp(self):
        reset_autodrive_runtime_state(clear_persistence=True)
        reset_github_issue_monitor_runtime_state(clear_persistence=True)
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(self._truncate_tables())

    def tearDown(self):
        asyncio.run(shutdown_github_issue_monitor_runtime())
        reset_github_issue_monitor_runtime_state(clear_persistence=True)
        reset_autodrive_runtime_state(clear_persistence=True)
        self.client.__exit__(None, None, None)
        asyncio.run(engine.dispose())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_issue_monitor_api_registers_lists_runs_once_and_removes(self):
        issue = {
            "id": 88,
            "number": 4519,
            "title": "UI 首屏太难理解",
            "body": "希望用户第一次打开就知道当前状态、下一步和入口。",
            "labels": ["ux", "bug"],
            "user": "lus",
            "state": "open",
            "html_url": "https://github.com/lusipad/KAM/issues/4519",
            "created_at": "2026-04-06T07:00:00Z",
            "updated_at": "2026-04-06T08:00:00Z",
            "comments_count": 1,
            "issue_comments": [
                {
                    "id": 7001,
                    "body": "最好默认就是新手视角。",
                    "user": "reviewer",
                    "html_url": "https://github.com/lusipad/KAM/issues/4519#issuecomment-7001",
                }
            ],
        }
        current_state = {
            "items": [issue],
            "meta": {"repo": "lusipad/KAM", "watch": "issues"},
        }
        changed_state = {"issues": [issue], "meta": current_state["meta"]}
        idle_state = {"issues": [], "meta": current_state["meta"]}
        actions = [{"kind": "create_run", "params": {"agent": "codex", "task": "处理 issue", "sourceIssueNumber": 4519}}]
        workspace = TMP_ROOT / "repo-workspace"

        with (
            patch("services.github_issue_monitors.ensure_repo_workspace", return_value=workspace),
            patch("services.github_issue_monitors.resolve_github_token", return_value="token"),
            patch("services.github_issue_monitors.GitHubAdapter", return_value=FakeAdapter(current_state, changed_state, actions)),
            patch(
                "services.github_issue_monitors.GlobalAutoDriveService.start",
                new=AsyncMock(
                    return_value=FakeControlResult(
                        {
                            "enabled": True,
                            "running": True,
                            "status": "running",
                            "summary": "已开启全局无人值守。",
                        }
                    )
                ),
            ),
        ):
            registered = self.client.post(
                "/api/issue-monitors",
                json={"repo": "lusipad/KAM", "repoPath": "D:/Repos/KAM", "runNow": True},
            ).json()

        self.assertEqual(registered["repo"], "lusipad/KAM")
        self.assertEqual(registered["repoPath"], "D:/Repos/KAM")
        self.assertEqual(registered["status"], "enqueued")
        self.assertTrue(registered["running"])
        self.assertEqual(len(registered["taskIds"]), 1)

        listed = self.client.get("/api/issue-monitors").json()["monitors"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["repo"], "lusipad/KAM")
        self.assertEqual(listed[0]["status"], "enqueued")

        tasks = self.client.get("/api/tasks").json()["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], registered["taskIds"][0])
        self.assertEqual(tasks[0]["metadata"]["sourceKind"], "github_issue")
        self.assertEqual(tasks[0]["metadata"]["sourceIssueNumber"], 4519)
        self.assertEqual(tasks[0]["metadata"]["sourceDedupKey"], "github_issue:lusipad/KAM:4519")

        with (
            patch("services.github_issue_monitors.ensure_repo_workspace", return_value=workspace),
            patch("services.github_issue_monitors.resolve_github_token", return_value="token"),
            patch("services.github_issue_monitors.GitHubAdapter", return_value=FakeAdapter(current_state, idle_state, actions)),
        ):
            manual = self.client.post("/api/issue-monitors/lusipad/KAM/run-once").json()

        self.assertEqual(manual["status"], "idle")
        self.assertEqual(manual["message"], "没有新的 GitHub issue 变化。")

        removed = self.client.delete("/api/issue-monitors/lusipad/KAM").json()
        self.assertTrue(removed["ok"])

        listed_after_remove = self.client.get("/api/issue-monitors").json()["monitors"]
        self.assertEqual(listed_after_remove, [])

    def test_recover_runtime_state_reschedules_registered_monitors(self):
        asyncio.run(upsert_issue_monitor("lusipad/KAM", "D:/Repos/KAM", app=None, run_now=False))
        fake_app = FastAPI()

        with (
            patch.object(type(config.settings), "is_test_env", new_callable=PropertyMock, return_value=False),
            patch("services.github_issue_monitors.schedule_issue_monitor_runtime", return_value=True) as schedule_mock,
        ):
            asyncio.run(recover_github_issue_monitor_runtime_state(fake_app))

        schedule_mock.assert_called_once()
        args = schedule_mock.call_args.args
        kwargs = schedule_mock.call_args.kwargs
        self.assertEqual(args[0], "lusipad/KAM")
        self.assertIs(args[1], fake_app)
        self.assertEqual(kwargs["initial_delay_seconds"], 1.0)

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


if __name__ == "__main__":
    unittest.main()
