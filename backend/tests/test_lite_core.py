import os
import shutil
import time
import unittest
from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


os.environ["DATABASE_URL"] = "sqlite:///./storage/test-lite-core.db"
os.environ["AGENT_WORKROOT"] = "./storage/test-lite-runs"

from app.main import app
from app.db.base import Base, engine


class LiteCoreApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        self.workroot = Path("./storage/test-lite-runs")
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

    def test_context_snapshot_contains_only_core_fields(self):
        with TestClient(app) as client:
            task = client.post("/api/tasks", json={"title": "Lite context", "description": "keep only core"}).json()

            ref = client.post(
                f"/api/tasks/{task['id']}/refs",
                json={"type": "repo-path", "label": "repo", "value": "D:/Repos/KAM"},
            )
            self.assertEqual(ref.status_code, 200)

            snapshot = client.post(f"/api/tasks/{task['id']}/context/resolve")
            self.assertEqual(snapshot.status_code, 200)

            payload = snapshot.json()
            self.assertEqual(set(payload["data"].keys()), {"task", "refs", "recentRuns"})
            self.assertEqual(payload["data"]["refs"][0]["type"], "repo-path")

    def test_custom_command_run_collects_review_and_artifacts(self):
        command = (
            "Write-Output 'run started'; "
            "Set-Content -Path (Join-Path '{run_dir}' 'final.md') -Value 'custom summary from test'; "
            "Write-Output 'run finished'"
        )

        with TestClient(app) as client:
            task = client.post("/api/tasks", json={"title": "Run smoke", "description": "exercise custom command"}).json()
            created = client.post(
                f"/api/tasks/{task['id']}/runs",
                json={"agents": [{"name": "smoke", "type": "custom", "command": command}]},
            )
            self.assertEqual(created.status_code, 200)

            run_id = created.json()["runs"][0]["id"]
            deadline = time.time() + 15
            run_payload = None

            while time.time() < deadline:
                response = client.get(f"/api/runs/{run_id}")
                self.assertEqual(response.status_code, 200)
                run_payload = response.json()
                if run_payload["status"] in {"completed", "failed", "canceled"}:
                    break
                time.sleep(0.25)

            self.assertIsNotNone(run_payload)
            self.assertEqual(run_payload["status"], "completed")

            artifacts = client.get(f"/api/runs/{run_id}/artifacts")
            self.assertEqual(artifacts.status_code, 200)
            artifact_types = {item["type"] for item in artifacts.json()["artifacts"]}
            self.assertTrue({"prompt", "context", "plan", "stdout", "stderr", "summary"}.issubset(artifact_types))

            review = client.get(f"/api/reviews/{task['id']}")
            self.assertEqual(review.status_code, 200)
            self.assertIn("运行数: 1", review.json()["summary"])

            comparison = client.post(f"/api/reviews/{task['id']}/compare", json={})
            self.assertEqual(comparison.status_code, 200)
            self.assertEqual(comparison.json()["comparison"][0]["status"], "completed")

    def test_autonomy_session_completes_with_checks_and_updates_metrics(self):
        command = (
            "Set-Content -Path (Join-Path '{run_dir}' 'done.txt') -Value 'ok'; "
            "Set-Content -Path (Join-Path '{run_dir}' 'final.md') -Value 'autonomy summary'; "
            "Write-Output 'autonomy finished'"
        )
        check_command = "if (!(Test-Path -LiteralPath (Join-Path '{run_dir}' 'done.txt'))) { throw 'missing done.txt'; }"

        with TestClient(app) as client:
            task = client.post("/api/tasks", json={"title": "Autonomy success", "description": "verify autonomy metrics"}).json()
            created = client.post(
                f"/api/tasks/{task['id']}/autonomy/sessions",
                json={
                    "title": "Autonomy smoke",
                    "objective": "complete once",
                    "primaryAgentName": "autonomy-smoke",
                    "primaryAgentType": "custom",
                    "primaryAgentCommand": command,
                    "maxIterations": 2,
                    "successCriteria": "done.txt exists",
                    "checkCommands": [{"label": "done marker", "command": check_command}],
                },
            )
            self.assertEqual(created.status_code, 200)
            session_id = created.json()["id"]

            started = client.post(f"/api/autonomy/sessions/{session_id}/start")
            self.assertEqual(started.status_code, 200)

            deadline = time.time() + 20
            session_payload = None
            while time.time() < deadline:
                response = client.get(f"/api/autonomy/sessions/{session_id}")
                self.assertEqual(response.status_code, 200)
                session_payload = response.json()
                if session_payload["status"] in {"completed", "failed", "interrupted"}:
                    break
                time.sleep(0.5)

            self.assertIsNotNone(session_payload)
            self.assertEqual(session_payload["status"], "completed")
            self.assertEqual(session_payload["cycles"][0]["status"], "passed")
            self.assertTrue(session_payload["cycles"][0]["checkResults"][0]["passed"])

            task_metrics = client.get(f"/api/tasks/{task['id']}/autonomy/metrics")
            self.assertEqual(task_metrics.status_code, 200)
            self.assertEqual(task_metrics.json()["completedSessions"], 1)
            self.assertEqual(task_metrics.json()["autonomyCompletionRate"], 1)
            self.assertEqual(task_metrics.json()["successRate"], 1)

    def test_autonomy_session_interrupt_increments_interruption_rate(self):
        command = (
            "Start-Sleep -Seconds 5; "
            "Set-Content -Path (Join-Path '{run_dir}' 'final.md') -Value 'too late'"
        )

        with TestClient(app) as client:
            task = client.post("/api/tasks", json={"title": "Autonomy interrupt", "description": "interrupt loop"}).json()
            created = client.post(
                f"/api/tasks/{task['id']}/autonomy/sessions",
                json={
                    "title": "Autonomy interrupt smoke",
                    "objective": "interrupt once",
                    "primaryAgentName": "interrupt-smoke",
                    "primaryAgentType": "custom",
                    "primaryAgentCommand": command,
                    "maxIterations": 2,
                    "checkCommands": [],
                },
            )
            self.assertEqual(created.status_code, 200)
            session_id = created.json()["id"]

            started = client.post(f"/api/autonomy/sessions/{session_id}/start")
            self.assertEqual(started.status_code, 200)

            deadline = time.time() + 10
            while time.time() < deadline:
                response = client.get(f"/api/autonomy/sessions/{session_id}")
                self.assertEqual(response.status_code, 200)
                if response.json()["status"] == "running":
                    break
                time.sleep(0.25)

            interrupted = client.post(f"/api/autonomy/sessions/{session_id}/interrupt")
            self.assertEqual(interrupted.status_code, 200)

            deadline = time.time() + 20
            session_payload = None
            while time.time() < deadline:
                response = client.get(f"/api/autonomy/sessions/{session_id}")
                self.assertEqual(response.status_code, 200)
                session_payload = response.json()
                if session_payload["status"] in {"completed", "failed", "interrupted"}:
                    break
                time.sleep(0.5)

            self.assertIsNotNone(session_payload)
            self.assertEqual(session_payload["status"], "interrupted")
            self.assertEqual(session_payload["interruptionCount"], 1)

            task_metrics = client.get(f"/api/tasks/{task['id']}/autonomy/metrics")
            self.assertEqual(task_metrics.status_code, 200)
            self.assertEqual(task_metrics.json()["interruptedSessions"], 1)
            self.assertEqual(task_metrics.json()["interruptionRate"], 1)

    def test_api_surface_is_lite_core_only(self):
        expected_routes = {
            ("GET", "/api/tasks"),
            ("POST", "/api/tasks"),
            ("GET", "/api/tasks/{task_id}"),
            ("PUT", "/api/tasks/{task_id}"),
            ("POST", "/api/tasks/{task_id}/archive"),
            ("POST", "/api/tasks/{task_id}/refs"),
            ("DELETE", "/api/tasks/{task_id}/refs/{ref_id}"),
            ("POST", "/api/tasks/{task_id}/context/resolve"),
            ("GET", "/api/context/snapshots/{snapshot_id}"),
            ("POST", "/api/tasks/{task_id}/runs"),
            ("GET", "/api/runs"),
            ("GET", "/api/runs/{run_id}"),
            ("POST", "/api/runs/{run_id}/start"),
            ("POST", "/api/runs/{run_id}/cancel"),
            ("POST", "/api/runs/{run_id}/retry"),
            ("GET", "/api/runs/{run_id}/artifacts"),
            ("GET", "/api/runs/{run_id}/events"),
            ("GET", "/api/reviews/{task_id}"),
            ("POST", "/api/reviews/{task_id}/compare"),
            ("GET", "/api/tasks/{task_id}/autonomy/sessions"),
            ("POST", "/api/tasks/{task_id}/autonomy/sessions"),
            ("POST", "/api/tasks/{task_id}/autonomy/dogfood"),
            ("GET", "/api/tasks/{task_id}/autonomy/metrics"),
            ("GET", "/api/autonomy/sessions/{session_id}"),
            ("POST", "/api/autonomy/sessions/{session_id}/start"),
            ("POST", "/api/autonomy/sessions/{session_id}/interrupt"),
            ("GET", "/api/autonomy/metrics"),
        }
        actual_routes = {
            (method, route.path)
            for route in app.routes
            if isinstance(route, APIRoute) and route.path.startswith("/api/")
            for method in route.methods
            if method in {"GET", "POST", "PUT", "DELETE"}
        }

        with TestClient(app) as client:
            self.assertEqual(actual_routes, expected_routes)
            self.assertEqual(client.get("/api/this-path-does-not-exist").status_code, 404)


if __name__ == "__main__":
    unittest.main()
