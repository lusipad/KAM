from __future__ import annotations

import json
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
os.environ["APP_ENV"] = "test"
os.environ.setdefault("ENABLE_LEGACY_V3", "true")

from db import async_session, engine  # noqa: E402
from main import app  # noqa: E402
from models import Message, Project, Run, Thread  # noqa: E402
from services.context import ContextAssembler  # noqa: E402
from services.digest import DigestService  # noqa: E402
from services.memory import MemoryService  # noqa: E402
from services.router import ConversationRouter  # noqa: E402
from services.run_engine import wait_for_background_runs  # noqa: E402


class V3ApiTests(unittest.TestCase):
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

    def test_project_thread_message_and_run_flow(self):
        project = self.client.post("/api/projects", json={"title": "信号探针", "repoPath": None}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "修复登录超时"}).json()

        async def fake_execute(_, run_id: str):
            async with async_session() as session:
                run = await session.get(Run, run_id)
                run.status = "passed"
                run.changed_files = ["auth.ts"]
                run.check_passed = True
                run.result_summary = "已更新 auth.ts，检查通过。"
                await session.commit()

        with patch("services.run_engine.RunEngine._execute_run", new=fake_execute):
            body = self._stream_message(thread["id"], "修复鉴权流程中的登录超时")

        self.assertIn("text_delta", body)
        self.assertIn("text_done", body)

        detail = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertEqual(detail["title"], "修复登录超时")
        self.assertGreaterEqual(len(detail["messages"]), 2)

        run = self._wait_for_run(detail["runs"][0]["id"])
        self.assertEqual(run["status"], "passed")
        self.assertEqual(run["changedFiles"], ["auth.ts"])

        feed = self.client.get("/api/home/feed").json()
        self.assertTrue(any(item["kind"] == "run" for item in feed["needsAttention"]))

    def test_memory_create_and_search(self):
        project = self.client.post("/api/projects", json={"title": "记忆实验室"}).json()
        created = self.client.post(
            "/api/memory",
            json={
                "projectId": project["id"],
                "category": "preference",
                "content": "测试要求：标记完成前必须先跑后端测试",
                "rationale": "这是用户明确提出的要求。",
            },
        ).json()
        self.assertEqual(created["category"], "preference")

        search = self.client.get("/api/memory/search", params={"project_id": project["id"], "query": "后端测试"}).json()
        self.assertEqual(len(search["memories"]), 1)
        self.assertIn("后端测试", search["memories"][0]["content"])

    def test_bootstrap_conversation_creates_project_and_thread_server_side(self):
        payload = self.client.post(
            "/api/projects/bootstrap",
            json={"prompt": "修复登录超时，并检查 token 刷新路径。", "repoPath": "D:/Repos/KAM"},
        ).json()

        self.assertEqual(payload["project"]["repoPath"], "D:/Repos/KAM")
        self.assertTrue(payload["project"]["title"])
        self.assertTrue(payload["thread"]["title"])
        self.assertNotEqual(payload["thread"]["title"], "新对话")

    def test_digest_failure_summary_suggests_next_step(self):
        run = Run(
            thread_id="thread123",
            agent="codex",
            status="failed",
            task="修复不稳定的 memory API 测试",
            raw_output="Traceback\nAssertionError: 预期 200，实际 204",
        )

        summary = asyncio.run(DigestService(None).summarize_run(run))

        self.assertIn("执行失败：", summary)
        self.assertIn("建议先查看最后一条报错并在修正后重试", summary)

    def test_digest_triage_strips_original_text_from_ai_draft(self):
        comment = {
            "id": "comment-1",
            "user": "reviewer",
            "path": "app/src/auth.ts",
            "line": 18,
            "body": "这里为什么不直接复用已有的 refresh 逻辑？",
        }
        payload = json.dumps(
            [
                {
                    "classification": "needs_input",
                    "draftReply": "这里为什么不直接复用已有的 refresh 逻辑？因为当前分支需要保留独立重试窗口。",
                    "fixPlan": "",
                }
            ],
            ensure_ascii=False,
        )

        service = DigestService(None)
        service.client = object()
        with patch.object(DigestService, "_complete_text", new=AsyncMock(return_value=payload)):
            cards = asyncio.run(service.triage_pr_comments([comment], ""))

        self.assertEqual(len(cards), 1)
        self.assertNotEqual(cards[0]["draftReply"], comment["body"])
        self.assertNotIn(comment["body"], cards[0]["draftReply"])
        self.assertIn("当前分支需要保留独立重试窗口", cards[0]["draftReply"])

    def test_watcher_run_now_creates_event(self):
        project = self.client.post("/api/projects", json={"title": "监控实验室"}).json()

        class FakeAdapter:
            async def fetch(self, config):
                return {"items": [{"id": 1, "title": "CI 失败", "head_branch": "main"}]}

            def diff(self, previous, current):
                return {"created": current["items"], "updated": []}

            def recommended_actions(self, watcher, changes):
                return [{"label": "自动修复", "kind": "create_run", "params": {"agent": "codex", "task": "修复 CI"}}]

            async def perform(self, action):
                return {"ok": True}

        with patch.dict("services.watcher.ADAPTERS", {"ci_pipeline": lambda: FakeAdapter()}):
            watcher = self.client.post(
                "/api/watchers",
                json={
                    "projectId": project["id"],
                    "name": "CI 监控",
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
        project = self.client.post("/api/projects", json={"title": "评审监控"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "PR 评审监控"}).json()

        body = self._stream_message(
            thread["id"],
            "监控 lusipad/KAM 的 PR #4518 review 评论，每 30 分钟检查一次，能自动修复的就直接修。",
        )

        self.assertIn("text_done", body)
        watcher = self.client.get("/api/watchers").json()["watchers"][0]
        self.assertEqual(watcher["sourceType"], "github_pr")
        self.assertEqual(watcher["scheduleValue"], "30m")
        self.assertEqual(watcher["autoActionLevel"], 2)
        self.assertEqual(watcher["status"], "draft")
        self.assertEqual(watcher["config"]["repo"], "lusipad/KAM")
        self.assertEqual(watcher["config"]["number"], 4518)
        self.assertEqual(watcher["config"]["watch"], "review_comments")

        detail = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertTrue(any(message["metadata"].get("kind") == "watcher-config" for message in detail["messages"]))

    def test_z_activate_draft_watcher_enables_it(self):
        project = self.client.post("/api/projects", json={"title": "草稿监控"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "配置 watcher"}).json()

        self._stream_message(
            thread["id"],
            "监控 lusipad/KAM 的 PR #4518 review 评论，每 30 分钟检查一次。",
        )

        watcher = self.client.get("/api/watchers").json()["watchers"][0]
        self.assertEqual(watcher["status"], "draft")

        with patch("services.watcher.WatcherEngine._schedule", new=lambda *_args, **_kwargs: None):
            activated = self.client.post(f"/api/watchers/{watcher['id']}/activate").json()
        self.assertEqual(activated["status"], "active")

    def test_router_honors_skill_and_agent_hints_for_runs(self):
        project = self.client.post("/api/projects", json={"title": "技能实验室"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "评审分流"}).json()

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
        self.assertIn("检查最新的 PR 评论", detail["runs"][0]["task"])
        self.assertIn("latest feedback", detail["runs"][0]["task"])

    def test_router_executes_tool_plan_from_model_blocks(self):
        project = self.client.post("/api/projects", json={"title": "模型编排"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "动作规划"}).json()

        events = asyncio.run(
            self._route_with_fake_model(
                thread_id=thread["id"],
                project_id=project["id"],
                content="以后默认先跑后端测试，然后修复 token 刷新。",
                blocks=[
                    self._fake_tool_block(
                        "record_memory",
                        {"category": "preference", "content": "默认先跑后端测试。", "rationale": "用户明确提出。"},
                    ),
                    self._fake_tool_block(
                        "create_run",
                        {"agent": "codex", "task": "[模型编排] 修复 token 刷新并验证后端测试"},
                    ),
                    self._fake_text_block("我已经把记忆和执行都安排好了。"),
                ],
            )
        )

        self.assertTrue(any(event["type"] == "tool_result" and event["tool"] == "record_memory" for event in events))
        self.assertTrue(any(event["type"] == "tool_result" and event["tool"] == "create_run" for event in events))
        self.assertTrue(any(event["type"] == "text_done" and "安排好了" in event["content"] for event in events))

        detail = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertEqual(len(detail["runs"]), 1)
        self.assertEqual(detail["runs"][0]["agent"], "codex")

        memories = self.client.get("/api/memory", params={"project_id": project["id"]}).json()["memories"]
        self.assertTrue(any(item["category"] == "preference" and "后端测试" in item["content"] for item in memories))

    def test_router_maps_commit_skill_to_run_task(self):
        project = self.client.post("/api/projects", json={"title": "提交实验室"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "提交助手"}).json()

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
        self.assertIn("创建一条干净的提交", detail["runs"][0]["task"])
        self.assertIn("message short and conventional", detail["runs"][0]["task"])

    def test_router_records_decision_memory(self):
        project = self.client.post("/api/projects", json={"title": "记忆路由"}).json()
        thread = self.client.post(f"/api/projects/{project['id']}/threads", json={"title": "架构记录"}).json()

        body = self._stream_message(thread["id"], "决定：V3 只保留 /api，去掉 /api/v2 兼容。")

        self.assertIn("text_done", body)
        memories = self.client.get("/api/memory", params={"project_id": project["id"]}).json()["memories"]
        self.assertTrue(any(item["category"] == "decision" and "只保留 /api" in item["content"] for item in memories))

    def test_router_continue_request_surfaces_recent_progress(self):
        thread_id = asyncio.run(self._seed_stale_thread())

        body = self._stream_message(thread_id, "继续昨天的工作")

        self.assertIn("text_done", body)
        self.assertIn("已调整重试退避", body)

    def test_memory_context_pack_supersedes_subject_duplicates_and_respects_budget(self):
        project = self.client.post("/api/projects", json={"title": "预算记忆"}).json()

        pack = asyncio.run(self._build_memory_pack(project["id"]))

        self.assertIn("## Active memory", pack["text"])
        self.assertIn("先跑后端测试，再跑 smoke", pack["text"])
        self.assertNotIn("只跑后端测试。", pack["text"])
        self.assertLessEqual(pack["budget"]["usedTokens"], 60)

    def test_context_build_returns_budgeted_prompt_context(self):
        thread_id = asyncio.run(self._seed_stale_thread())

        context = asyncio.run(self._build_context(thread_id, "继续昨天的工作"))

        self.assertIn("## Current project", context["prompt_context"])
        self.assertIn("## Recent context", context["prompt_context"])
        self.assertTrue(context["has_recent_activity"])
        self.assertLessEqual(context["budget"]["usedTokens"], context["budget"]["totalTokens"])

    def test_watcher_detail_update_and_history(self):
        project = self.client.post("/api/projects", json={"title": "监控管理"}).json()

        class FakeAdapter:
            async def fetch(self, config):
                return {"items": [{"id": 18, "title": "评审队列增长", "head_branch": "main"}]}

            def diff(self, previous, current):
                return {"created": current["items"], "updated": []}

            def recommended_actions(self, watcher, changes):
                return [{"label": "检查事件", "kind": "create_run", "params": {"agent": "codex", "task": "检查监控事件"}}]

            async def perform(self, action):
                return {"ok": True}

        with patch.dict("services.watcher.ADAPTERS", {"ci_pipeline": lambda: FakeAdapter()}):
            watcher = self.client.post(
                "/api/watchers",
                json={
                    "projectId": project["id"],
                    "name": "构建监控",
                    "sourceType": "ci_pipeline",
                    "config": {"repo": "owner/repo", "provider": "github_actions"},
                    "scheduleType": "interval",
                    "scheduleValue": "15m",
                    "autoActionLevel": 1,
                },
            ).json()
            self.client.post(f"/api/watchers/{watcher['id']}/run-now")

        detail = self.client.get(f"/api/watchers/{watcher['id']}").json()
        self.assertEqual(detail["name"], "构建监控")
        self.assertEqual(detail["scheduleValue"], "15m")

        updated = self.client.put(
            f"/api/watchers/{watcher['id']}",
            json={"name": "构建监控 v2", "scheduleValue": "30m", "autoActionLevel": 2},
        ).json()
        self.assertEqual(updated["name"], "构建监控 v2")
        self.assertEqual(updated["scheduleValue"], "30m")
        self.assertEqual(updated["autoActionLevel"], 2)

        events = self.client.get(f"/api/watchers/{watcher['id']}/events").json()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "main 分支 CI 失败")
        self.assertEqual(events[0]["watcher"]["name"], "构建监控 v2")

    def test_get_thread_appends_restore_summary_once_for_stale_thread(self):
        thread_id = asyncio.run(self._seed_stale_thread())

        first_detail = self.client.get(f"/api/threads/{thread_id}").json()
        restore_messages = [message for message in first_detail["messages"] if message["metadata"].get("kind") == "restore-summary"]
        self.assertEqual(len(restore_messages), 1)
        self.assertIn("上次做到这里：", restore_messages[0]["content"])
        self.assertIn("已调整重试退避", restore_messages[0]["content"])

        second_detail = self.client.get(f"/api/threads/{thread_id}").json()
        second_restore_messages = [message for message in second_detail["messages"] if message["metadata"].get("kind") == "restore-summary"]
        self.assertEqual(len(second_restore_messages), 1)

    def test_dev_seed_demo_populates_v3_workspace_data(self):
        payload = self.client.post("/api/dev/seed-demo", json={"reset": True}).json()
        self.assertEqual(payload["projectId"], "demo-noise")
        self.assertEqual(payload["threadId"], "demo-login")

        threads = self.client.get("/api/threads").json()["threads"]
        self.assertEqual(len(threads), 4)
        self.assertEqual(threads[0]["project"]["title"], "信号探针")

        feed = self.client.get("/api/home/feed").json()
        self.assertEqual(len(feed["needsAttention"]), 3)
        self.assertEqual(len(feed["running"]), 1)
        self.assertEqual(len(feed["recent"]), 1)
        self.assertTrue(any(item["kind"] == "watcher_event" for item in feed["needsAttention"]))
        self.assertEqual(feed["recent"][0]["id"], "demo-run-adopted")

        detail = self.client.get("/api/threads/demo-login").json()
        self.assertEqual(detail["title"], "修复登录超时")
        self.assertEqual(detail["runs"][0]["status"], "passed")

        memories = self.client.get("/api/memory", params={"project_id": "demo-noise"}).json()["memories"]
        self.assertEqual({item["category"] for item in memories}, {"preference", "decision", "learning"})

    def test_home_feed_prioritizes_failed_runs_before_watcher_alerts_and_adoptions(self):
        self.client.post("/api/dev/seed-demo", json={"reset": True})

        feed = self.client.get("/api/home/feed").json()

        self.assertEqual(feed["needsAttention"][0]["kind"], "run")
        self.assertEqual(feed["needsAttention"][0]["status"], "failed")
        self.assertEqual(feed["needsAttention"][1]["kind"], "watcher_event")
        self.assertEqual(feed["needsAttention"][2]["kind"], "run")
        self.assertEqual(feed["needsAttention"][2]["status"], "passed")

    def test_home_feed_recent_only_shows_historical_runs(self):
        self.client.post("/api/dev/seed-demo", json={"reset": True})

        feed = self.client.get("/api/home/feed").json()
        recent_ids = {item["id"] for item in feed["recent"]}
        attention_ids = {item["id"] for item in feed["needsAttention"] if item["kind"] == "run"}

        self.assertEqual(recent_ids, {"demo-run-adopted"})
        self.assertTrue(recent_ids.isdisjoint(attention_ids))

    def test_task_ref_snapshot_run_artifacts_and_compare_flow(self):
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "切换到 harness 主线",
                "description": "把当前 V3 工作台切到 task-first harness。",
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

    def test_missing_resources_return_chinese_404_details(self):
        thread_response = self.client.get("/api/threads/missing-thread")
        watcher_response = self.client.get("/api/watchers/missing-watcher")
        memory_response = self.client.put("/api/memory/missing-memory", json={"content": "补一条"})

        self.assertEqual(thread_response.status_code, 404)
        self.assertEqual(thread_response.json()["detail"], "线程不存在")
        self.assertEqual(watcher_response.status_code, 404)
        self.assertEqual(watcher_response.json()["detail"], "监控不存在")
        self.assertEqual(memory_response.status_code, 404)
        self.assertEqual(memory_response.json()["detail"], "记忆不存在")

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
            for table in (
                "review_compares",
                "task_run_artifacts",
                "task_runs",
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
            project = Project(title="恢复实验室")
            session.add(project)
            await session.flush()

            thread = Thread(
                project_id=project.id,
                title="继续修复支付重试",
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
                        content="周末发版前把支付重试流程修好。",
                        created_at=base + timedelta(minutes=1),
                    ),
                    Message(
                        thread_id=thread.id,
                        role="assistant",
                        content="我已经针对计费链路启动了一次聚焦执行。",
                        created_at=base + timedelta(minutes=2),
                    ),
                    Run(
                        thread_id=thread.id,
                        agent="codex",
                        status="passed",
                        task="修复支付重试流程",
                        result_summary="已调整重试退避，并补上 API 覆盖。",
                        changed_files=["backend/payments.py", "backend/tests/test_payments.py"],
                        check_passed=True,
                        duration_ms=980,
                        raw_output="2 项测试通过",
                        created_at=base + timedelta(minutes=3),
                    ),
                ]
            )
            await session.commit()
            return thread.id

    async def _route_with_fake_model(self, *, thread_id: str, project_id: str, content: str, blocks: list[object]) -> list[dict]:
        class FakeMessages:
            def __init__(self, response_blocks: list[object]):
                self._response_blocks = response_blocks

            async def create(self, **_kwargs):
                return type("FakeResponse", (), {"content": self._response_blocks})()

        async def fake_create_run(router_run_engine, *, thread_id: str, agent: str, task: str):
            run = Run(thread_id=thread_id, agent=agent, task=task, status="pending")
            router_run_engine.db.add(run)
            await router_run_engine.db.commit()
            await router_run_engine.db.refresh(run)
            return run

        async with async_session() as session:
            router = ConversationRouter(session)
            router.client = type("FakeClient", (), {"messages": FakeMessages(blocks)})()
            with patch("services.router.RunEngine.create_run", new=fake_create_run):
                return await router.route_message(thread_id=thread_id, message_content=content, project_id=project_id)

    async def _build_memory_pack(self, project_id: str) -> dict:
        async with async_session() as session:
            service = MemoryService(session)
            first = await service.record(
                project_id=project_id,
                category="preference",
                content="默认测试顺序：只跑后端测试。",
            )
            replacement = await service.record(
                project_id=project_id,
                category="preference",
                content="默认测试顺序：先跑后端测试，再跑 smoke。",
            )
            await service.record(
                project_id=project_id,
                category="decision",
                content="提交前必须跑本地 smoke。",
            )
            await session.refresh(first)
            pack = await service.build_context_pack(
                project_id,
                "后端测试 smoke",
                always_budget_tokens=40,
                relevant_budget_tokens=20,
            )
            assert first.superseded_by == replacement.id
            return pack

    async def _build_context(self, thread_id: str, query: str) -> dict:
        async with async_session() as session:
            thread = await session.get(Thread, thread_id)
            return await ContextAssembler(session).build(thread_id=thread_id, project_id=thread.project_id, query=query)

    def _fake_text_block(self, text: str):
        return type("FakeTextBlock", (), {"type": "text", "text": text})()

    def _fake_tool_block(self, name: str, payload: dict[str, object]):
        return type("FakeToolBlock", (), {"type": "tool_use", "name": name, "input": payload})()
