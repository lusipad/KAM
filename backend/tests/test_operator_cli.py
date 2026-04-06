from __future__ import annotations

import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "operator_cli.py"


def _task_record(task_id: str, title: str) -> dict[str, object]:
    return {
        "id": task_id,
        "title": title,
        "description": None,
        "repoPath": "D:/Repos/KAM",
        "status": "in_progress",
        "priority": "high",
        "labels": ["dogfood"],
        "metadata": {},
        "archivedAt": None,
        "createdAt": "2026-04-06T00:00:00Z",
        "updatedAt": "2026-04-06T00:00:00Z",
    }


def _control_plane(*, system_status: str = "ready", enabled: bool = False) -> dict[str, object]:
    focus_task = _task_record("task-harness-cutover", "切到 task-first harness")
    return {
        "generatedAt": "2026-04-06T00:00:00Z",
        "systemStatus": system_status,
        "systemSummary": "当前有任务可继续推进。" if system_status != "attention" else "有失败任务等待人工介入。",
        "globalAutoDrive": {
            "enabled": enabled,
            "running": enabled,
            "status": "running" if enabled else "idle",
            "summary": "全局无人值守运行中。" if enabled else "当前无人值守未开启。",
            "lastAction": None,
            "lastReason": None,
            "currentTaskId": focus_task["id"],
            "currentScopeTaskId": focus_task["id"],
            "currentRunId": None,
            "loopCount": 3,
            "error": None,
            "updatedAt": "2026-04-06T00:00:00Z",
            "lease": None,
            "recentEvents": [],
        },
        "stats": {
            "totalTaskCount": 1,
            "runnableTaskCount": 1,
            "blockedTaskCount": 0,
            "failedTaskCount": 0 if system_status != "attention" else 1,
            "pendingRunCount": 0,
            "runningRunCount": 0,
            "passedRunAwaitingAdoptCount": 0,
            "scopeAutodriveEnabledCount": 0,
        },
        "focus": {
            "task": focus_task,
            "scopeTask": focus_task,
            "activeRun": None,
            "summary": "当前焦点任务是切到 task-first harness。",
            "reason": "focus_task",
        },
        "actions": [
            {
                "key": "continue_task_family",
                "label": "继续推进当前任务",
                "description": "围绕当前 task family 重新判断 adopt / retry / plan / dispatch。",
                "tone": "green",
                "taskId": focus_task["id"],
                "runId": None,
                "disabled": False,
                "disabledReason": None,
            },
            {
                "key": "restart_global_autodrive",
                "label": "重启全局 supervisor",
                "description": "重新拉起全局无人值守 supervisor。",
                "tone": "amber",
                "taskId": None,
                "runId": None,
                "disabled": False,
                "disabledReason": None,
            },
        ],
        "attention": []
        if system_status != "attention"
        else [
            {
                "kind": "failed_run",
                "title": "最近失败",
                "summary": "有失败任务等待人工介入。",
                "tone": "amber",
                "taskId": focus_task["id"],
                "runId": None,
            }
        ],
        "recentEvents": [],
    }


class _OperatorCliHandler(BaseHTTPRequestHandler):
    server: "_OperatorCliServer"

    def log_message(self, format: str, *args) -> None:
        return None

    def _send_json(self, payload: dict[str, object], *, status_code: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        self.server.paths.append(("GET", parsed.path, parse_qs(parsed.query)))
        if parsed.path == "/api/operator/control-plane":
            self._send_json(self.server.control_plane)
            return
        self._send_json({"detail": "not found"}, status_code=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw else {}
        self.server.paths.append(("POST", parsed.path, payload))
        if parsed.path == "/api/operator/actions":
            self.server.action_payloads.append(payload)
            action = payload.get("action")
            control_plane = _control_plane(enabled=action == "start_global_autodrive")
            response = {
                "ok": True,
                "action": action,
                "summary": f"执行动作：{action}",
                "taskId": payload.get("taskId"),
                "runId": payload.get("runId"),
                "continueDecision": None,
                "controlPlane": control_plane,
            }
            self._send_json(response)
            return
        self._send_json({"detail": "not found"}, status_code=404)


class _OperatorCliServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _OperatorCliHandler)
        self.control_plane = _control_plane()
        self.action_payloads: list[dict[str, object]] = []
        self.paths: list[tuple[str, str, object]] = []


class OperatorCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _OperatorCliServer()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/api"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_status_json_returns_control_plane(self):
        completed = self._run_cli("status", "--kam-url", self.base_url, "--json")

        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout.strip())
        self.assertEqual(payload["systemStatus"], "ready")
        self.assertEqual(payload["focus"]["task"]["id"], "task-harness-cutover")

    def test_status_fail_on_attention_exits_two(self):
        self.server.control_plane = _control_plane(system_status="attention")

        completed = self._run_cli("status", "--kam-url", self.base_url, "--fail-on-attention")

        self.assertEqual(completed.returncode, 2)
        self.assertIn("状态: 待介入", completed.stdout)
        self.assertIn("需要关注:", completed.stdout)

    def test_action_alias_posts_operator_action(self):
        completed = self._run_cli("restart-global", "--kam-url", self.base_url, "--json")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(self.server.action_payloads[0]["action"], "restart_global_autodrive")
        payload = json.loads(completed.stdout.strip())
        self.assertEqual(payload["action"], "restart_global_autodrive")

    def test_watch_json_respects_iteration_limit(self):
        completed = self._run_cli("watch", "--kam-url", self.base_url, "--json", "--interval-seconds", "0.01", "--iterations", "2")

        self.assertEqual(completed.returncode, 0)
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(json.loads(line)["systemStatus"] == "ready" for line in lines))


if __name__ == "__main__":
    unittest.main()
