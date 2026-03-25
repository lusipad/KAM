import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


os.environ["DATABASE_URL"] = "sqlite:///./storage/test-v2-preview.db"
os.environ["AGENT_WORKROOT"] = "./storage/test-v2-runs"
os.environ["OPENAI_API_KEY"] = ""

from app.main import app
from app.core.config import settings
from app.db.base import Base, engine


class V2WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        self.workroot = Path("./storage/test-v2-runs")
        if self.workroot.exists():
            self._remove_workroot()
        self.workroot.mkdir(parents=True, exist_ok=True)

    def _remove_workroot(self):
        deadline = time.time() + 5
        while True:
            try:
                shutil.rmtree(self.workroot)
                return
            except PermissionError:
                if time.time() >= deadline:
                    raise
                time.sleep(0.25)

    def _wait_run(self, client: TestClient, run_id: str, timeout: float = 20):
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = client.get(f"/api/v2/runs/{run_id}")
            self.assertEqual(response.status_code, 200)
            last_payload = response.json()
            if last_payload["status"] in {"passed", "failed", "cancelled"}:
                return last_payload
            time.sleep(0.25)
        self.fail(f"run {run_id} not finished in time, last={last_payload}")

    def test_project_thread_message_and_run_flow(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={
                    "title": "KAM v2",
                    "description": "workspace project",
                    "checkCommands": ["test -f '{run_dir}/done.txt'" if os.name != "nt" else "if (!(Test-Path -LiteralPath (Join-Path '{run_dir}' 'done.txt'))) { throw 'missing done.txt'; }"],
                },
            )
            self.assertEqual(project.status_code, 200)
            project_payload = project.json()
            self.assertEqual(project_payload["title"], "KAM v2")

            thread = client.post(
                f"/api/v2/projects/{project_payload['id']}/threads",
                json={"title": "继续昨天的工作"},
            )
            self.assertEqual(thread.status_code, 200)
            thread_payload = thread.json()

            command = (
                "if [ -f '{run_dir}/first-pass.flag' ]; then printf '%s' 'ok' > '{run_dir}/done.txt'; printf '%s' 'retry fixed' > '{summary_file}'; "
                "else touch '{run_dir}/first-pass.flag'; printf '%s' 'first round' > '{summary_file}'; fi"
                if os.name != "nt"
                else "if (Test-Path -LiteralPath (Join-Path '{run_dir}' 'first-pass.flag')) { Set-Content -Path (Join-Path '{run_dir}' 'done.txt') -Value 'ok'; Set-Content -Path '{summary_file}' -Value 'retry fixed'; } else { Set-Content -Path (Join-Path '{run_dir}' 'first-pass.flag') -Value '1'; Set-Content -Path '{summary_file}' -Value 'first round'; }"
            )
            created = client.post(
                f"/api/v2/threads/{thread_payload['id']}/runs",
                json={
                    "agent": "custom",
                    "command": command,
                    "prompt": "实现 token refresh",
                    "autoStart": True,
                    "maxRounds": 2,
                },
            )
            self.assertEqual(created.status_code, 200)
            created_payload = created.json()
            self.assertEqual(created_payload["status"], "pending")

            run_payload = self._wait_run(client, created_payload["id"])
            self.assertEqual(run_payload["status"], "passed")
            self.assertEqual(run_payload["round"], 2)

            artifacts = client.get(f"/api/v2/runs/{created_payload['id']}/artifacts")
            self.assertEqual(artifacts.status_code, 200)
            artifact_types = {item["type"] for item in artifacts.json()["artifacts"]}
            self.assertTrue({"prompt", "context", "stdout", "stderr", "summary", "check_result", "feedback"}.issubset(artifact_types))

            thread_detail = client.get(f"/api/v2/threads/{thread_payload['id']}")
            self.assertEqual(thread_detail.status_code, 200)
            thread_payload_detail = thread_detail.json()
            self.assertGreaterEqual(len(thread_payload_detail["runs"]), 1)
            event_types = {item.get("metadata", {}).get("eventType") for item in thread_payload_detail["messages"]}
            self.assertIn("run-created", event_types)
            self.assertIn("run-passed", event_types)

    def test_project_file_tree_endpoint(self):
        with tempfile.TemporaryDirectory() as repo_dir:
            repo_root = Path(repo_dir)
            (repo_root / 'src').mkdir(parents=True, exist_ok=True)
            (repo_root / 'docs').mkdir(parents=True, exist_ok=True)
            (repo_root / 'src' / 'main.ts').write_text('console.log("kam")', encoding='utf-8')
            (repo_root / 'docs' / 'notes.md').write_text('# notes', encoding='utf-8')
            (repo_root / '.secret').write_text('hidden', encoding='utf-8')

            with TestClient(app) as client:
                project = client.post(
                    '/api/v2/projects',
                    json={
                        'title': 'Files project',
                        'repoPath': str(repo_root),
                    },
                ).json()

                root_listing = client.get(f"/api/v2/projects/{project['id']}/files")
                self.assertEqual(root_listing.status_code, 200)
                payload = root_listing.json()
                self.assertEqual(payload['currentPath'], '')
                names = [item['name'] for item in payload['entries']]
                self.assertIn('src', names)
                self.assertIn('docs', names)
                self.assertNotIn('.secret', names)

                nested_listing = client.get(
                    f"/api/v2/projects/{project['id']}/files",
                    params={'path': 'src'},
                )
                self.assertEqual(nested_listing.status_code, 200)
                nested_payload = nested_listing.json()
                self.assertEqual(nested_payload['currentPath'], 'src')
                self.assertEqual(nested_payload['parentPath'], '')
                self.assertEqual(nested_payload['entries'][0]['name'], 'main.ts')

                hidden_listing = client.get(
                    f"/api/v2/projects/{project['id']}/files",
                    params={'include_hidden': 'true'},
                )
                self.assertEqual(hidden_listing.status_code, 200)
                hidden_names = [item['name'] for item in hidden_listing.json()['entries']]
                self.assertIn('.secret', hidden_names)

                filtered_listing = client.get(
                    f"/api/v2/projects/{project['id']}/files",
                    params={'query': 'src', 'entry_type': 'dir'},
                )
                self.assertEqual(filtered_listing.status_code, 200)
                filtered_payload = filtered_listing.json()
                self.assertEqual(filtered_payload['totalEntries'], 2)
                self.assertEqual(filtered_payload['filteredEntries'], 1)
                self.assertEqual(filtered_payload['entries'][0]['name'], 'src')

    def test_run_events_endpoint_streams_payload(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={"title": "Events project"},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={"title": "事件流"},
            ).json()

            command = (
                "printf '%s' 'event done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'event done'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/runs",
                json={
                    "agent": "custom",
                    "command": command,
                    "prompt": "事件流验证",
                    "autoStart": True,
                },
            ).json()
            run_payload = self._wait_run(client, created["id"])
            self.assertEqual(run_payload["status"], "passed")

            with client.stream("GET", f"/api/v2/runs/{created['id']}/events") as response:
                self.assertEqual(response.status_code, 200)
                body = ''.join(response.iter_text())
            self.assertIn('data: ', body)
            self.assertIn('"status": "passed"', body)
            self.assertIn('summary', body)

    def test_memory_endpoints(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={"title": "Memory project"},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={"title": "记忆测试"},
            ).json()

            preference = client.post(
                "/api/v2/memory/preferences",
                json={
                    "category": "tool",
                    "key": "package-manager",
                    "value": "pnpm",
                    "sourceThreadId": thread["id"],
                },
            )
            self.assertEqual(preference.status_code, 200)

            updated = client.put(
                f"/api/v2/memory/preferences/{preference.json()['id']}",
                json={"value": "pnpm-workspace"},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["value"], "pnpm-workspace")

            decision = client.post(
                "/api/v2/memory/decisions",
                json={
                    "projectId": project["id"],
                    "question": "状态管理选什么？",
                    "decision": "Zustand",
                    "reasoning": "足够轻量",
                    "sourceThreadId": thread["id"],
                },
            )
            self.assertEqual(decision.status_code, 200)

            updated_decision = client.put(
                f"/api/v2/memory/decisions/{decision.json()['id']}",
                json={
                    "question": "状态管理最终选什么？",
                    "decision": "Jotai",
                    "reasoning": "这次想要更细粒度",
                },
            )
            self.assertEqual(updated_decision.status_code, 200)
            self.assertEqual(updated_decision.json()["decision"], "Jotai")

            learning = client.post(
                "/api/v2/memory/learnings",
                json={
                    "projectId": project["id"],
                    "content": "OAuth refresh 需要处理 race condition",
                    "embedding": [0.1, 0.2],
                    "sourceThreadId": thread["id"],
                },
            )
            self.assertEqual(learning.status_code, 200)

            updated_learning = client.put(
                f"/api/v2/memory/learnings/{learning.json()['id']}",
                json={
                    "content": "OAuth refresh 还要处理 race condition、并发刷新和 token 覆盖",
                    "embedding": [0.2, 0.3],
                },
            )
            self.assertEqual(updated_learning.status_code, 200)
            self.assertIn("并发刷新", updated_learning.json()["content"])

            listing = client.get(
                "/api/v2/memory/learnings",
                params={"project_id": project["id"]},
            )
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(len(listing.json()["learnings"]), 1)

            search = client.get(
                "/api/v2/memory/search",
                params={"query": "race", "project_id": project["id"]},
            )
            self.assertEqual(search.status_code, 200)
            self.assertEqual(len(search.json()["learnings"]), 1)

    def test_learning_auto_generates_embedding_when_key_available(self):
        class FakeEmbeddingResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'data': [
                        {
                            'embedding': [0.11, 0.22, 0.33],
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.memory_service.httpx.post', return_value=FakeEmbeddingResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        "/api/v2/projects",
                        json={"title": "Embedding project"},
                    ).json()

                    learning = client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "OAuth refresh 需要处理 race condition 和并发刷新覆盖",
                        },
                    )
                    self.assertEqual(learning.status_code, 200)
                    self.assertEqual(learning.json()["embedding"], [0.11, 0.22, 0.33])
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_memory_search_prefers_semantic_learning_matches(self):
        class FakeEmbeddingResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'data': [
                        {
                            'embedding': [1.0, 0.0],
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.memory_service.httpx.post', return_value=FakeEmbeddingResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        "/api/v2/projects",
                        json={"title": "Semantic search project"},
                    ).json()

                    first = client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "处理 OAuth refresh token 的并发覆盖",
                            "embedding": [1.0, 0.0],
                        },
                    )
                    second = client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "构建发布脚本要处理环境变量模板",
                            "embedding": [0.0, 1.0],
                        },
                    )
                    self.assertEqual(first.status_code, 200)
                    self.assertEqual(second.status_code, 200)

                    result = client.get(
                        "/api/v2/memory/search",
                        params={"query": "怎么避免 refresh token 竞态", "project_id": project["id"]},
                    )
                    self.assertEqual(result.status_code, 200)
                    learnings = result.json()["learnings"]
                    self.assertGreaterEqual(len(learnings), 1)
                    self.assertEqual(learnings[0]["content"], "处理 OAuth refresh token 的并发覆盖")
                    self.assertIn("semanticScore", learnings[0])
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_compare_endpoint_creates_grouped_runs(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={"title": "Compare project"},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={"title": "并发对比"},
            ).json()

            command_a = (
                "printf '%s' 'A done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'A done'"
            )
            command_b = (
                "printf '%s' 'B done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'B done'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/compare",
                json={
                    "prompt": "分别实现 refresh token 流程并对比",
                    "agents": [
                        {"agent": "custom", "label": "方案 A", "command": command_a},
                        {"agent": "custom", "label": "方案 B", "command": command_b},
                    ],
                    "autoStart": True,
                },
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()
            self.assertTrue(payload["compareId"])
            self.assertEqual(len(payload["runs"]), 2)
            self.assertEqual(payload["message"]["role"], "system")

            first = self._wait_run(client, payload["runs"][0]["id"])
            second = self._wait_run(client, payload["runs"][1]["id"])
            self.assertEqual(first["status"], "passed")
            self.assertEqual(second["status"], "passed")
            self.assertEqual(first["metadata"]["compareGroupId"], payload["compareId"])
            self.assertEqual(second["metadata"]["compareGroupId"], payload["compareId"])

            thread_detail = client.get(f"/api/v2/threads/{thread['id']}")
            self.assertEqual(thread_detail.status_code, 200)
            runs = thread_detail.json()["runs"]
            compare_runs = [item for item in runs if item["metadata"].get("compareGroupId") == payload["compareId"]]
            self.assertEqual(len(compare_runs), 2)

    def test_message_router_auto_creates_run_and_extracts_preference(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={
                    'title': 'Router project',
                    'checkCommands': ["test -f '{run_dir}/done.txt'" if os.name != "nt" else "if (!(Test-Path -LiteralPath (Join-Path '{run_dir}' 'done.txt'))) { throw 'missing done.txt'; }"],
                },
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Router thread'},
            ).json()

            command = (
                "printf '%s' 'ok' > '{run_dir}/done.txt'; printf '%s' 'router fixed' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path (Join-Path '{run_dir}' 'done.txt') -Value 'ok'; Set-Content -Path '{summary_file}' -Value 'router fixed'"
            )
            posted = client.post(
                f"/api/v2/threads/{thread['id']}/messages",
                json={
                    'content': '以后默认用 pnpm，继续修复登录模块',
                    'agent': 'custom',
                    'command': command,
                },
            )
            self.assertEqual(posted.status_code, 200)
            payload = posted.json()
            self.assertEqual(len(payload['runs']), 1)
            self.assertEqual(payload['preferences'][0]['key'], 'package-manager')
            self.assertIsNotNone(payload['reply'])
            self.assertIn('自动创建 1 个 custom run', payload['reply']['content'])
            self.assertEqual(payload['routerMode'], 'heuristic')

            run_payload = self._wait_run(client, payload['runs'][0]['id'])
            self.assertEqual(run_payload['status'], 'passed')

            preferences = client.get('/api/v2/memory/preferences')
            self.assertEqual(preferences.status_code, 200)
            self.assertEqual(preferences.json()['preferences'][0]['value'], 'pnpm')

    def test_bootstrap_message_creates_project_thread_and_run(self):
        with TestClient(app) as client:
            command = (
                "printf '%s' 'ok' > '{run_dir}/done.txt'; printf '%s' 'bootstrap done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path (Join-Path '{run_dir}' 'done.txt') -Value 'ok'; Set-Content -Path '{summary_file}' -Value 'bootstrap done'"
            )
            created = client.post(
                '/api/v2/bootstrap/message',
                json={
                    'projectTitle': '认证模块重构',
                    'threadTitle': '首轮分析',
                    'content': '以后默认用 pnpm，继续修复登录模块',
                    'agent': 'custom',
                    'command': command,
                    'checkCommands': ["test -f '{run_dir}/done.txt'" if os.name != "nt" else "if (!(Test-Path -LiteralPath (Join-Path '{run_dir}' 'done.txt'))) { throw 'missing done.txt'; }"],
                },
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()
            self.assertEqual(payload['project']['title'], '认证模块重构')
            self.assertEqual(payload['thread']['title'], '首轮分析')
            self.assertEqual(payload['message']['role'], 'user')
            self.assertEqual(payload['reply']['role'], 'assistant')
            self.assertEqual(len(payload['runs']), 1)
            self.assertEqual(payload['preferences'][0]['key'], 'package-manager')

            run_payload = self._wait_run(client, payload['runs'][0]['id'])
            self.assertEqual(run_payload['status'], 'passed')

            thread_detail = client.get(f"/api/v2/threads/{payload['thread']['id']}")
            self.assertEqual(thread_detail.status_code, 200)
            self.assertGreaterEqual(len(thread_detail.json()['messages']), 2)

    def test_user_message_auto_extracts_resources_to_project(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Resources project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': '资源抽取'},
            ).json()

            posted = client.post(
                f"/api/v2/threads/{thread['id']}/messages",
                json={
                    'content': '请参考 https://example.com/spec ，并查看 src/auth/refresh.py 和 docs/design/auth-flow.md',
                    'createRun': False,
                },
            )
            self.assertEqual(posted.status_code, 200)

            project_detail = client.get(f"/api/v2/projects/{project['id']}")
            self.assertEqual(project_detail.status_code, 200)
            resources = project_detail.json()['resources']
            uris = {item['uri'] for item in resources}
            self.assertIn('https://example.com/spec', uris)
            self.assertIn('src/auth/refresh.py', uris)
            self.assertIn('docs/design/auth-flow.md', uris)
            self.assertTrue(all(item['metadata'].get('autoExtracted') for item in resources))

    def test_router_reply_references_history_preferences_and_decisions(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Memory reply project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Memory reply thread'},
            ).json()

            preference = client.post(
                '/api/v2/memory/preferences',
                json={
                    'category': 'tool',
                    'key': 'package-manager',
                    'value': 'pnpm',
                    'sourceThreadId': thread['id'],
                },
            )
            self.assertEqual(preference.status_code, 200)

            decision = client.post(
                '/api/v2/memory/decisions',
                json={
                    'projectId': project['id'],
                    'question': '状态管理选什么？',
                    'decision': 'Zustand',
                    'reasoning': '足够轻量',
                    'sourceThreadId': thread['id'],
                },
            )
            self.assertEqual(decision.status_code, 200)

            learning = client.post(
                '/api/v2/memory/learnings',
                json={
                    'projectId': project['id'],
                    'content': 'OAuth refresh 要处理 race condition 与并发刷新覆盖。',
                    'sourceThreadId': thread['id'],
                },
            )
            self.assertEqual(learning.status_code, 200)

            posted = client.post(
                f"/api/v2/threads/{thread['id']}/messages",
                json={
                    'content': '先聊聊这个项目下一步',
                    'createRun': False,
                },
            )
            self.assertEqual(posted.status_code, 200)
            payload = posted.json()
            self.assertIn('package-manager=pnpm', payload['reply']['content'])
            self.assertIn('状态管理选什么？ → Zustand', payload['reply']['content'])
            self.assertIn('OAuth refresh 要处理 race condition', payload['reply']['content'])

    def test_thread_events_endpoint_streams_payload(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Thread events project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': '事件流线程'},
            ).json()

            command = (
                "printf '%s' 'thread event done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'thread event done'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/runs",
                json={
                    'agent': 'custom',
                    'command': command,
                    'prompt': '线程事件流验证',
                    'autoStart': True,
                },
            ).json()
            run_payload = self._wait_run(client, created['id'])
            self.assertEqual(run_payload['status'], 'passed')

            with client.stream('GET', f"/api/v2/threads/{thread['id']}/events") as response:
                self.assertEqual(response.status_code, 200)
                body = ''.join(response.iter_text())
            self.assertIn('data: ', body)
            self.assertIn('"thread"', body)
            self.assertIn('"runs"', body)

    def test_message_stream_endpoint_streams_reply_and_result(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Message stream project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'SSE 消息线程'},
            ).json()

            with client.stream(
                'POST',
                f"/api/v2/threads/{thread['id']}/messages/stream",
                json={
                    'content': '先聊聊这个项目下一步',
                    'createRun': False,
                },
            ) as response:
                self.assertEqual(response.status_code, 200)
                body = ''.join(response.iter_text())

            self.assertIn('event: message-saved', body)
            self.assertIn('event: assistant-reply-delta', body)
            self.assertIn('event: assistant-reply-complete', body)
            self.assertIn('event: result', body)
            self.assertIn('event: done', body)
            self.assertIn('我已把这条消息记入当前 Thread', body)

    def test_message_endpoint_supports_sse_via_accept_header(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Message accept stream project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Accept SSE 线程'},
            ).json()

            with client.stream(
                'POST',
                f"/api/v2/threads/{thread['id']}/messages",
                headers={'Accept': 'text/event-stream'},
                json={
                    'content': '只通过主入口接收 SSE',
                    'createRun': False,
                },
            ) as response:
                self.assertEqual(response.status_code, 200)
                body = ''.join(response.iter_text())

            self.assertIn('event: message-saved', body)
            self.assertIn('event: result', body)
            self.assertIn('event: done', body)

    def test_llm_router_function_call_records_decision_without_run(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [
                        {
                            'message': {
                                'tool_calls': [
                                    {
                                        'type': 'function',
                                        'function': {
                                            'name': 'plan_kam_response',
                                            'arguments': (
                                                '{'
                                                '"should_run": false, '
                                                '"mode": "chat", '
                                                '"agents": [], '
                                                '"preferences": [], '
                                                '"decisions": ['
                                                '{"question": "状态管理方案选哪个？", "decision": "Zustand", "reasoning": "足够轻量"}'
                                                '], '
                                                '"learnings": [], '
                                                '"summary": "已记录你的决策，本轮先不执行。"}'
                                            ),
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.conversation_router.httpx.post', return_value=FakeResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        '/api/v2/projects',
                        json={'title': 'LLM router project'},
                    ).json()
                    thread = client.post(
                        f"/api/v2/projects/{project['id']}/threads",
                        json={'title': 'LLM router thread'},
                    ).json()

                    posted = client.post(
                        f"/api/v2/threads/{thread['id']}/messages",
                        json={
                            'content': '状态管理就定 Zustand，先不要执行。',
                        },
                    )
                    self.assertEqual(posted.status_code, 200)
                    payload = posted.json()
                    self.assertEqual(payload['routerMode'], 'llm')
                    self.assertEqual(payload['runs'], [])
                    self.assertIn('已记录你的决策', payload['reply']['content'])

                    decisions = client.get(
                        '/api/v2/memory/decisions',
                        params={'project_id': project['id']},
                    )
                    self.assertEqual(decisions.status_code, 200)
                    self.assertEqual(len(decisions.json()['decisions']), 1)
                    self.assertEqual(decisions.json()['decisions'][0]['decision'], 'Zustand')
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_passed_run_auto_creates_project_learning(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Auto learning project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': '自动 learning'},
            ).json()

            command = (
                "printf '%s' '实现了 token refresh，并处理 race condition 和并发覆盖。' > '{summary_file}'"
                if os.name != 'nt'
                else "Set-Content -Path '{summary_file}' -Value '实现了 token refresh，并处理 race condition 和并发覆盖。'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/runs",
                json={
                    'agent': 'custom',
                    'command': command,
                    'prompt': '实现 refresh token',
                    'autoStart': True,
                },
            ).json()
            run_payload = self._wait_run(client, created['id'])
            self.assertEqual(run_payload['status'], 'passed')

            learnings = client.get('/api/v2/memory/learnings', params={'project_id': project['id']})
            self.assertEqual(learnings.status_code, 200)
            contents = [item['content'] for item in learnings.json()['learnings']]
            self.assertTrue(any('race condition' in content for content in contents))

    def test_adopt_compare_run_records_decision_memory(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Adopt compare project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Compare adopt'},
            ).json()

            command_a = (
                "printf '%s' '方案 A：实现 refresh token，并增加 race condition 保护。' > '{summary_file}'"
                if os.name != 'nt'
                else "Set-Content -Path '{summary_file}' -Value '方案 A：实现 refresh token，并增加 race condition 保护。'"
            )
            command_b = (
                "printf '%s' '方案 B：实现 refresh token，并增加缓存。' > '{summary_file}'"
                if os.name != 'nt'
                else "Set-Content -Path '{summary_file}' -Value '方案 B：实现 refresh token，并增加缓存。'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/compare",
                json={
                    'prompt': '分别实现 refresh token 流程并对比',
                    'agents': [
                        {'agent': 'custom', 'label': '方案 A', 'command': command_a},
                        {'agent': 'custom', 'label': '方案 B', 'command': command_b},
                    ],
                    'autoStart': True,
                },
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()

            first = self._wait_run(client, payload['runs'][0]['id'])
            second = self._wait_run(client, payload['runs'][1]['id'])
            self.assertEqual(first['status'], 'passed')
            self.assertEqual(second['status'], 'passed')

            adopted = client.post(f"/api/v2/runs/{payload['runs'][0]['id']}/adopt")
            self.assertEqual(adopted.status_code, 200)

            decisions = client.get('/api/v2/memory/decisions', params={'project_id': project['id']})
            self.assertEqual(decisions.status_code, 200)
            rows = decisions.json()['decisions']
            self.assertTrue(any(item['question'] == '分别实现 refresh token 流程并对比' for item in rows))
            self.assertTrue(any(item['decision'] == '方案 A' for item in rows))


if __name__ == "__main__":
    unittest.main()
