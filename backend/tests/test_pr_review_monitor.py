from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

SCRIPT_PATH = BACKEND_ROOT / "scripts" / "pr_review_monitor.py"
SPEC = importlib.util.spec_from_file_location("pr_review_monitor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
pr_review_monitor = importlib.util.module_from_spec(SPEC)
sys.modules.setdefault("pr_review_monitor", pr_review_monitor)
SPEC.loader.exec_module(pr_review_monitor)


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


class PRReviewMonitorTests(unittest.TestCase):
    def test_build_commit_message_uses_lore_trailers(self):
        message = pr_review_monitor._build_commit_message(
            repo="lusipad/KAM",
            pull_number=4518,
            comments=[
                {
                    "path": "backend/services/router.py",
                    "html_url": "https://github.com/lusipad/KAM/pull/4518#discussion_r1",
                }
            ],
        )

        self.assertIn("Constraint:", message)
        self.assertIn("Confidence:", message)
        self.assertIn("Scope-risk:", message)
        self.assertIn("Reversibility:", message)
        self.assertIn("Directive:", message)
        self.assertIn("Tested:", message)
        self.assertIn("Not-tested:", message)
        self.assertIn("Related:", message)

    def test_main_does_not_advance_state_when_codex_run_fails(self):
        current_state = {
            "items": [{"id": 9, "body": "Please reuse helper", "path": "backend/services/router.py", "updated_at": "2026-04-04T00:00:00Z"}],
            "meta": {"repo": "lusipad/KAM", "watch": "review_comments", "number": 4518, "headRef": "feature/pr-4518", "headRepo": "lusipad/KAM"},
        }
        changes = {"review_comments": current_state["items"], "meta": current_state["meta"]}
        actions = [{"kind": "create_run", "params": {"task": "处理评审"}}]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            args = argparse.Namespace(
                repo="lusipad/KAM",
                pr=4518,
                codex_path="codex.cmd",
                kam_url="",
                output_dir=str(output_dir),
                dry_run=False,
            )
            finalize_mock = patch.object(pr_review_monitor, "_finalize_and_push", return_value=None)
            with (
                patch.object(pr_review_monitor, "parse_args", return_value=args),
                patch.object(pr_review_monitor, "_ensure_base_clone"),
                patch.object(pr_review_monitor, "_resolve_github_token", return_value="token"),
                patch.object(pr_review_monitor, "GitHubPRAdapter", return_value=FakeAdapter(current_state, changes, actions)),
                patch.object(pr_review_monitor, "_resolve_codex", return_value="codex.cmd"),
                patch.object(
                    pr_review_monitor,
                    "_prepare_pr_worktree",
                    return_value=(output_dir / "worktree", "abc123", "origin", "feature/pr-4518", "lusipad/KAM"),
                ),
                patch.object(pr_review_monitor, "_run_codex", return_value=CompletedProcess(["codex"], 1, stdout="failed", stderr="")),
                patch.object(pr_review_monitor, "_git_head", return_value="abc123"),
                patch.object(pr_review_monitor, "_git_status", return_value=" M backend/services/router.py"),
                finalize_mock as mocked_finalize,
            ):
                rc = pr_review_monitor.main()

            self.assertEqual(rc, 1)
            self.assertFalse((output_dir / "state.json").exists())
            summary = json.loads((output_dir / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "run-failed")
            mocked_finalize.assert_not_called()

    def test_main_advances_state_after_successful_push(self):
        current_state = {
            "items": [{"id": 9, "body": "Please reuse helper", "path": "backend/services/router.py", "updated_at": "2026-04-04T00:00:00Z"}],
            "meta": {"repo": "lusipad/KAM", "watch": "review_comments", "number": 4518, "headRef": "feature/pr-4518", "headRepo": "lusipad/KAM"},
        }
        changes = {"review_comments": current_state["items"], "meta": current_state["meta"]}
        actions = [{"kind": "create_run", "params": {"task": "处理评审"}}]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            args = argparse.Namespace(
                repo="lusipad/KAM",
                pr=4518,
                codex_path="codex.cmd",
                kam_url="",
                output_dir=str(output_dir),
                dry_run=False,
            )
            with (
                patch.object(pr_review_monitor, "parse_args", return_value=args),
                patch.object(pr_review_monitor, "_ensure_base_clone"),
                patch.object(pr_review_monitor, "_resolve_github_token", return_value="token"),
                patch.object(pr_review_monitor, "GitHubPRAdapter", return_value=FakeAdapter(current_state, changes, actions)),
                patch.object(pr_review_monitor, "_resolve_codex", return_value="codex.cmd"),
                patch.object(
                    pr_review_monitor,
                    "_prepare_pr_worktree",
                    return_value=(output_dir / "worktree", "abc123", "origin", "feature/pr-4518", "lusipad/KAM"),
                ),
                patch.object(pr_review_monitor, "_run_codex", return_value=CompletedProcess(["codex"], 0, stdout="ok", stderr="")),
                patch.object(pr_review_monitor, "_git_head", return_value="abc123"),
                patch.object(pr_review_monitor, "_git_status", return_value=" M backend/services/router.py"),
                patch.object(pr_review_monitor, "_finalize_and_push", return_value="def456"),
                patch.object(pr_review_monitor, "_remove_worktree"),
            ):
                rc = pr_review_monitor.main()

            self.assertEqual(rc, 0)
            saved_state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_state, current_state)
            self.assertEqual(summary["status"], "pushed")
            self.assertEqual(summary["pushedCommit"], "def456")
            self.assertIsNone(summary["worktree"])

    def test_main_enqueues_kam_task_and_starts_autodrive(self):
        current_state = {
            "items": [{"id": 9, "body": "Please reuse helper", "path": "backend/services/router.py", "updated_at": "2026-04-04T00:00:00Z"}],
            "meta": {
                "repo": "lusipad/KAM",
                "watch": "review_comments",
                "number": 4518,
                "headRef": "feature/pr-4518",
                "headSha": "abc123",
                "headRepo": "lusipad/KAM",
                "pullUrl": "https://github.com/lusipad/KAM/pull/4518",
            },
        }
        changes = {"review_comments": current_state["items"], "meta": current_state["meta"]}
        actions = [{"kind": "create_run", "params": {"agent": "codex", "task": "处理评审"}}]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            args = argparse.Namespace(
                repo="lusipad/KAM",
                pr=4518,
                codex_path="codex.cmd",
                kam_url="http://127.0.0.1:8000/api",
                output_dir=str(output_dir),
                dry_run=False,
            )
            with (
                patch.object(pr_review_monitor, "parse_args", return_value=args),
                patch.object(pr_review_monitor, "_ensure_base_clone"),
                patch.object(pr_review_monitor, "_resolve_github_token", return_value="token"),
                patch.object(pr_review_monitor, "GitHubPRAdapter", return_value=FakeAdapter(current_state, changes, actions)),
                patch.object(pr_review_monitor, "_enqueue_task_to_harness", return_value={"id": "taskkam0001"}),
                patch.object(
                    pr_review_monitor,
                    "_start_harness_global_autodrive",
                    return_value={"enabled": True, "running": True, "status": "running"},
                ),
                patch.object(pr_review_monitor, "_resolve_codex") as mocked_resolve_codex,
            ):
                rc = pr_review_monitor.main()

            self.assertEqual(rc, 0)
            mocked_resolve_codex.assert_not_called()
            saved_state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_state, current_state)
            self.assertEqual(summary["status"], "enqueued")
            self.assertEqual(summary["taskMode"], "harness_queue")
            self.assertEqual(summary["taskId"], "taskkam0001")
            self.assertTrue(summary["autodrive"]["enabled"])


if __name__ == "__main__":
    unittest.main()
