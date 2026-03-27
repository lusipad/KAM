from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text


TMP_ROOT = Path(tempfile.mkdtemp(prefix="kam-v3-tests-"))
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP_ROOT / 'kam-v3.db').as_posix()}"
os.environ["STORAGE_PATH"] = str(TMP_ROOT)
os.environ["RUN_ROOT"] = str(TMP_ROOT / "runs")
os.environ["ANTHROPIC_API_KEY"] = ""

from db import async_session, engine  # noqa: E402
from main import app  # noqa: E402
from models import Run  # noqa: E402


class V3ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(self._truncate_tables())

    def tearDown(self):
        self.client.__exit__(None, None, None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_project_thread_message_and_run_flow(self):
        project = self.client.post("/api/projects", json={"title": "Noise Probe", "repoPath": None}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "Fix login timeout"}).json()

        async def fake_execute(_, run_id: str):
            async with async_session() as session:
                run = await session.get(Run, run_id)
                run.status = "passed"
                run.changed_files = ["auth.ts"]
                run.check_passed = True
                run.result_summary = "Updated auth.ts and passed the check."
                await session.commit()

        with patch("services.run_engine.RunEngine._execute_run", new=fake_execute):
            with self.client.stream(
                "POST",
                f"/api/threads/{thread['id']}/messages",
                json={"content": "Fix login timeout in the auth flow"},
            ) as response:
                self.assertEqual(response.status_code, 200)
                body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

        self.assertIn("text_delta", body)
        self.assertIn("text_done", body)

        detail = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertEqual(detail["title"], "Fix login timeout")
        self.assertGreaterEqual(len(detail["messages"]), 2)

        run = self._wait_for_run(detail["runs"][0]["id"])
        self.assertEqual(run["status"], "passed")
        self.assertEqual(run["changedFiles"], ["auth.ts"])

        feed = self.client.get("/api/home/feed").json()
        self.assertTrue(any(item["kind"] == "run" for item in feed["needsAttention"]))

    def test_memory_create_and_search(self):
        project = self.client.post("/api/projects", json={"title": "Memory Lab"}).json()
        created = self.client.post(
            "/api/memory",
            json={
                "projectId": project["id"],
                "category": "preference",
                "content": "Testing: always run backend tests before marking done",
                "rationale": "User explicitly asked for it.",
            },
        ).json()
        self.assertEqual(created["category"], "preference")

        search = self.client.get("/api/memory/search", params={"project_id": project["id"], "query": "backend tests"}).json()
        self.assertEqual(len(search["memories"]), 1)
        self.assertIn("backend tests", search["memories"][0]["content"])

    def test_watcher_run_now_creates_event(self):
        project = self.client.post("/api/projects", json={"title": "Watcher Lab"}).json()

        class FakeAdapter:
            async def fetch(self, config):
                return {"items": [{"id": 1, "title": "CI red", "head_branch": "main"}]}

            def diff(self, previous, current):
                return {"created": current["items"], "updated": []}

            def recommended_actions(self, watcher, changes):
                return [{"label": "Auto-fix", "kind": "create_run", "params": {"agent": "codex", "task": "Fix CI"}}]

            async def perform(self, action):
                return {"ok": True}

        with patch.dict("services.watcher.ADAPTERS", {"ci_pipeline": lambda: FakeAdapter()}):
            watcher = self.client.post(
                "/api/watchers",
                json={
                    "projectId": project["id"],
                    "name": "CI monitor",
                    "sourceType": "ci_pipeline",
                    "config": {"repo": "owner/repo", "provider": "github_actions"},
                    "scheduleType": "interval",
                    "scheduleValue": "15m",
                },
            ).json()
            event_payload = self.client.post(f"/api/watchers/{watcher['id']}/run-now").json()

        self.assertEqual(event_payload["event"]["eventType"], "ci_failed")
        self.assertEqual(event_payload["event"]["status"], "pending")

    def test_dev_seed_demo_populates_v3_workspace_data(self):
        payload = self.client.post("/api/dev/seed-demo", json={"reset": True}).json()
        self.assertEqual(payload["projectId"], "demo-noise")
        self.assertEqual(payload["threadId"], "demo-login")

        threads = self.client.get("/api/threads").json()["threads"]
        self.assertEqual(len(threads), 2)
        self.assertEqual(threads[0]["project"]["title"], "Noise Probe")

        feed = self.client.get("/api/home/feed").json()
        self.assertEqual(len(feed["needsAttention"]), 3)
        self.assertTrue(any(item["kind"] == "watcher_event" for item in feed["needsAttention"]))

        detail = self.client.get("/api/threads/demo-login").json()
        self.assertEqual(detail["title"], "Fix login timeout")
        self.assertEqual(detail["runs"][0]["status"], "passed")

        memories = self.client.get("/api/memory", params={"project_id": "demo-noise"}).json()["memories"]
        self.assertEqual({item["category"] for item in memories}, {"preference", "decision", "learning"})

    def _wait_for_run(self, run_id: str, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            run = self.client.get(f"/api/runs/{run_id}").json()
            if run["status"] in {"passed", "failed"}:
                return run
            time.sleep(0.1)
        self.fail(f"run {run_id} did not finish in time")

    async def _truncate_tables(self):
        async with engine.begin() as conn:
            for table in ("watcher_events", "watchers", "memories", "runs", "messages", "threads", "projects"):
                await conn.execute(text(f'DELETE FROM "{table}"'))
