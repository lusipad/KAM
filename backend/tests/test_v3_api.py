from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sse_starlette.sse import AppStatus
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
from models import Message, Project, Run, Thread  # noqa: E402
from services.digest import DigestService  # noqa: E402
class V3ApiTests(unittest.TestCase):
    def setUp(self):
        AppStatus.should_exit_event = asyncio.Event()
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(self._truncate_tables())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        asyncio.run(engine.dispose())

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
            body = self._stream_message(thread["id"], "Fix login timeout in the auth flow")

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

    def test_digest_failure_summary_suggests_next_step(self):
        run = Run(
            thread_id="thread123",
            agent="codex",
            status="failed",
            task="Fix the flaky memory API test",
            raw_output="Traceback\nAssertionError: expected 200 but received 204",
        )

        summary = asyncio.run(DigestService(None).summarize_run(run))

        self.assertIn("执行失败：", summary)
        self.assertIn("建议先查看最后一条报错并在修正后重试", summary)

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

    def test_router_parses_github_review_watcher_from_natural_language(self):
        project = self.client.post("/api/projects", json={"title": "Review Watch"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "Review monitor"}).json()

        body = self._stream_message(
            thread["id"],
            "Monitor lusipad/KAM PR #4518 for review comments every 30m and auto-fix what you can.",
        )

        self.assertIn("text_done", body)
        watcher = self.client.get("/api/watchers").json()["watchers"][0]
        self.assertEqual(watcher["sourceType"], "github_pr")
        self.assertEqual(watcher["scheduleValue"], "30m")
        self.assertEqual(watcher["autoActionLevel"], 2)
        self.assertEqual(watcher["config"]["repo"], "lusipad/KAM")
        self.assertEqual(watcher["config"]["number"], 4518)
        self.assertEqual(watcher["config"]["watch"], "review_comments")

        detail = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertTrue(any(message["metadata"].get("kind") == "watcher-config" for message in detail["messages"]))

    def test_router_honors_skill_and_agent_hints_for_runs(self):
        project = self.client.post("/api/projects", json={"title": "Skill Lab"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "Review triage"}).json()

        async def fake_create_run(router_run_engine, *, thread_id: str, agent: str, task: str):
            run = Run(thread_id=thread_id, agent=agent, task=task, status="pending")
            router_run_engine.db.add(run)
            await router_run_engine.db.commit()
            await router_run_engine.db.refresh(run)
            return run

        with patch("services.router.RunEngine.create_run", new=fake_create_run):
            body = self._stream_message(thread["id"], "/review-pr use claude-code on the latest feedback")

        self.assertIn("text_done", body)
        detail = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertEqual(len(detail["runs"]), 1)
        self.assertEqual(detail["runs"][0]["agent"], "claude-code")
        self.assertIn("Review the latest PR comments", detail["runs"][0]["task"])
        self.assertIn("latest feedback", detail["runs"][0]["task"])

    def test_router_maps_commit_skill_to_run_task(self):
        project = self.client.post("/api/projects", json={"title": "Commit Lab"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "Commit helper"}).json()

        async def fake_create_run(router_run_engine, *, thread_id: str, agent: str, task: str):
            run = Run(thread_id=thread_id, agent=agent, task=task, status="pending")
            router_run_engine.db.add(run)
            await router_run_engine.db.commit()
            await router_run_engine.db.refresh(run)
            return run

        with patch("services.router.RunEngine.create_run", new=fake_create_run):
            body = self._stream_message(thread["id"], "/commit make the message short and conventional")

        self.assertIn("text_done", body)
        detail = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertEqual(len(detail["runs"]), 1)
        self.assertEqual(detail["runs"][0]["agent"], "codex")
        self.assertIn("create a clean commit", detail["runs"][0]["task"])
        self.assertIn("message short and conventional", detail["runs"][0]["task"])

    def test_router_records_decision_memory(self):
        project = self.client.post("/api/projects", json={"title": "Memory Router"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "Architecture notes"}).json()

        body = self._stream_message(thread["id"], "Decision: V3 uses /api only and drops /api/v2 compatibility.")

        self.assertIn("text_done", body)
        memories = self.client.get("/api/memory", params={"project_id": project["id"]}).json()["memories"]
        self.assertTrue(any(item["category"] == "decision" and "/api only" in item["content"] for item in memories))

    def test_router_continue_request_surfaces_recent_progress(self):
        thread_id = asyncio.run(self._seed_stale_thread())

        body = self._stream_message(thread_id, "继续昨天的工作")

        self.assertIn("text_done", body)
        self.assertIn("Patched retry backoff", body)

    def test_watcher_detail_update_and_history(self):
        project = self.client.post("/api/projects", json={"title": "Watcher Admin"}).json()

        class FakeAdapter:
            async def fetch(self, config):
                return {"items": [{"id": 18, "title": "Review queue growing", "head_branch": "main"}]}

            def diff(self, previous, current):
                return {"created": current["items"], "updated": []}

            def recommended_actions(self, watcher, changes):
                return [{"label": "Inspect", "kind": "create_run", "params": {"agent": "codex", "task": "Inspect watcher event"}}]

            async def perform(self, action):
                return {"ok": True}

        with patch.dict("services.watcher.ADAPTERS", {"ci_pipeline": lambda: FakeAdapter()}):
            watcher = self.client.post(
                "/api/watchers",
                json={
                    "projectId": project["id"],
                    "name": "Build monitor",
                    "sourceType": "ci_pipeline",
                    "config": {"repo": "owner/repo", "provider": "github_actions"},
                    "scheduleType": "interval",
                    "scheduleValue": "15m",
                    "autoActionLevel": 1,
                },
            ).json()
            self.client.post(f"/api/watchers/{watcher['id']}/run-now")

        detail = self.client.get(f"/api/watchers/{watcher['id']}").json()
        self.assertEqual(detail["name"], "Build monitor")
        self.assertEqual(detail["scheduleValue"], "15m")

        updated = self.client.put(
            f"/api/watchers/{watcher['id']}",
            json={"name": "Build monitor v2", "scheduleValue": "30m", "autoActionLevel": 2},
        ).json()
        self.assertEqual(updated["name"], "Build monitor v2")
        self.assertEqual(updated["scheduleValue"], "30m")
        self.assertEqual(updated["autoActionLevel"], 2)

        events = self.client.get(f"/api/watchers/{watcher['id']}/events").json()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "CI failed on main")
        self.assertEqual(events[0]["watcher"]["name"], "Build monitor v2")

    def test_get_thread_appends_restore_summary_once_for_stale_thread(self):
        thread_id = asyncio.run(self._seed_stale_thread())

        first_detail = self.client.get(f"/api/threads/{thread_id}").json()
        restore_messages = [message for message in first_detail["messages"] if message["metadata"].get("kind") == "restore-summary"]
        self.assertEqual(len(restore_messages), 1)
        self.assertIn("上次做到这里：", restore_messages[0]["content"])
        self.assertIn("Patched retry backoff", restore_messages[0]["content"])

        second_detail = self.client.get(f"/api/threads/{thread_id}").json()
        second_restore_messages = [message for message in second_detail["messages"] if message["metadata"].get("kind") == "restore-summary"]
        self.assertEqual(len(second_restore_messages), 1)

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

    def _stream_message(self, thread_id: str, content: str) -> str:
        with self.client.stream(
            "POST",
            f"/api/threads/{thread_id}/messages",
            json={"content": content},
        ) as response:
            self.assertEqual(response.status_code, 200)
            return "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    async def _seed_stale_thread(self) -> str:
        base = datetime.now(UTC) - timedelta(days=3)
        async with async_session() as session:
            project = Project(title="Restore Lab")
            session.add(project)
            await session.flush()

            thread = Thread(
                project_id=project.id,
                title="Resume payment fix",
                created_at=base,
                updated_at=base + timedelta(minutes=3),
            )
            session.add(thread)
            await session.flush()

            session.add_all(
                [
                    Message(
                        thread_id=thread.id,
                        role="user",
                        content="Fix the payment retry flow before the weekend release.",
                        created_at=base + timedelta(minutes=1),
                    ),
                    Message(
                        thread_id=thread.id,
                        role="assistant",
                        content="I started a focused run against the billing path.",
                        created_at=base + timedelta(minutes=2),
                    ),
                    Run(
                        thread_id=thread.id,
                        agent="codex",
                        status="passed",
                        task="Fix payment retry flow",
                        result_summary="Patched retry backoff and added API coverage.",
                        changed_files=["backend/payments.py", "backend/tests/test_payments.py"],
                        check_passed=True,
                        duration_ms=980,
                        raw_output="2 tests passed",
                        created_at=base + timedelta(minutes=3),
                    ),
                ]
            )
            await session.commit()
            return thread.id
