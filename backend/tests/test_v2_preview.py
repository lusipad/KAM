import os
import shutil
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


os.environ["DATABASE_URL"] = "sqlite:///./storage/test-v2-preview.db"
os.environ["AGENT_WORKROOT"] = "./storage/test-v2-runs"
os.environ["OPENAI_API_KEY"] = ""

from app.main import app
from app.db.base import Base, engine


class V2PreviewApiTests(unittest.TestCase):
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
                    "description": "preview project",
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
            self.assertGreaterEqual(len(thread_detail.json()["runs"]), 1)

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

            search = client.get(
                "/api/v2/memory/search",
                params={"query": "race", "project_id": project["id"]},
            )
            self.assertEqual(search.status_code, 200)
            self.assertEqual(len(search.json()["learnings"]), 1)

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


if __name__ == "__main__":
    unittest.main()
