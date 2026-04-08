from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

SCRIPT_PATH = BACKEND_ROOT / "scripts" / "github_issue_monitor.py"
SPEC = importlib.util.spec_from_file_location("github_issue_monitor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
github_issue_monitor = importlib.util.module_from_spec(SPEC)
sys.modules.setdefault("github_issue_monitor", github_issue_monitor)
SPEC.loader.exec_module(github_issue_monitor)


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


class GitHubIssueMonitorTests(unittest.TestCase):
    def test_main_is_idle_when_no_issue_changes(self):
        current_state = {
            "items": [],
            "meta": {"repo": "lusipad/KAM", "watch": "issues"},
        }
        changes = {"issues": [], "meta": current_state["meta"]}
        actions: list[dict] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            workspace = output_dir / "repo"
            args = argparse.Namespace(
                repo="lusipad/KAM",
                kam_url="http://127.0.0.1:8000/api",
                repo_path="",
                output_dir=str(output_dir),
                dry_run=False,
            )
            with (
                patch.object(github_issue_monitor, "parse_args", return_value=args),
                patch.object(github_issue_monitor, "ensure_repo_workspace", return_value=workspace),
                patch.object(github_issue_monitor, "resolve_github_token", return_value="token"),
                patch.object(github_issue_monitor, "GitHubAdapter", return_value=FakeAdapter(current_state, changes, actions)),
            ):
                rc = github_issue_monitor.main()

            self.assertEqual(rc, 0)
            saved_state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_state, current_state)
            self.assertEqual(summary["status"], "idle")
            self.assertEqual(summary["message"], "没有新的 GitHub issue 变化。")

    def test_main_enqueues_kam_tasks_and_starts_autodrive(self):
        issue = {
            "id": 88,
            "number": 4519,
            "title": "UI 首屏太难理解",
            "body": "希望用户第一次打开就知道当前状态、下一步和入口。",
            "labels": ["ux", "bug"],
            "user": "lus",
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
        changes = {"issues": [issue], "meta": current_state["meta"]}
        actions = [{"kind": "create_run", "params": {"agent": "codex", "task": "处理 issue", "sourceIssueNumber": 4519}}]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            workspace = output_dir / "repo"
            args = argparse.Namespace(
                repo="lusipad/KAM",
                kam_url="http://127.0.0.1:8000/api",
                repo_path="",
                output_dir=str(output_dir),
                dry_run=False,
            )
            with (
                patch.object(github_issue_monitor, "parse_args", return_value=args),
                patch.object(github_issue_monitor, "ensure_repo_workspace", return_value=workspace),
                patch.object(github_issue_monitor, "resolve_github_token", return_value="token"),
                patch.object(github_issue_monitor, "GitHubAdapter", return_value=FakeAdapter(current_state, changes, actions)),
                patch.object(github_issue_monitor, "enqueue_task_to_harness", return_value={"id": "taskkam0001"}) as mocked_enqueue,
                patch.object(
                    github_issue_monitor,
                    "start_harness_global_autodrive",
                    return_value={"enabled": True, "running": True, "status": "running"},
                ),
            ):
                rc = github_issue_monitor.main()

            self.assertEqual(rc, 0)
            enqueue_args = mocked_enqueue.call_args.args
            self.assertEqual(enqueue_args[0], "http://127.0.0.1:8000/api")
            payload = enqueue_args[1]
            self.assertEqual(payload["metadata"]["sourceKind"], "github_issue")
            self.assertEqual(payload["metadata"]["sourceDedupKey"], "github_issue:lusipad/KAM:4519")
            self.assertEqual(payload["metadata"]["sourceIssueNumber"], 4519)
            self.assertEqual(payload["repoPath"], str(workspace))
            self.assertTrue(any(ref.get("metadata", {}).get("intakeSourceKind") == "github_issue" for ref in payload["refs"]))

            saved_state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_state, current_state)
            self.assertEqual(summary["status"], "enqueued")
            self.assertEqual(summary["taskMode"], "harness_queue")
            self.assertEqual(summary["taskIds"], ["taskkam0001"])
            self.assertEqual(summary["issueNumbers"], [4519])
            self.assertIn("已同步到 KAM 任务池", summary["message"])
            self.assertTrue(summary["autodrive"]["enabled"])


if __name__ == "__main__":
    unittest.main()
