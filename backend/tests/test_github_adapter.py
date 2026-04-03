from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("GITHUB_TOKEN", "")

from adapters.github import GitHubPRAdapter  # noqa: E402


class GitHubPRAdapterTests(unittest.TestCase):
    def test_init_falls_back_to_git_credentials_when_env_token_missing(self):
        created_tokens: list[str | None] = []

        class FakeGhApi:
            def __init__(self, token=None):
                created_tokens.append(token)

        with (
            patch("adapters.github.settings.github_token", ""),
            patch("adapters.github._load_git_credential_token", return_value="credential-token"),
            patch("adapters.github.GhApi", FakeGhApi),
        ):
            adapter = GitHubPRAdapter()

        self.assertEqual(created_tokens, ["credential-token"])
        self.assertEqual(adapter._token, "credential-token")

    def test_diff_only_surfaces_new_or_updated_review_comments(self):
        adapter = GitHubPRAdapter()
        previous = {
            "items": [
                {"id": 11, "updated_at": "2026-04-03T00:00:00Z", "body": "old", "path": "a.py", "line": 7},
                {"id": 13, "updated_at": "2026-04-04T00:30:00Z", "body": "updated", "path": "c.py", "line": 12},
            ],
            "meta": {"repo": "lusipad/KAM", "watch": "review_comments", "number": 4518},
        }
        current = {
            "items": [
                {"id": 11, "updated_at": "2026-04-03T00:00:00Z", "body": "old", "path": "a.py", "line": 7},
                {"id": 12, "updated_at": "2026-04-04T00:00:00Z", "body": "new", "path": "b.py", "line": 9},
                {"id": 13, "updated_at": "2026-04-04T01:00:00Z", "body": "updated", "path": "c.py", "line": 12},
            ],
            "meta": {"repo": "lusipad/KAM", "watch": "review_comments", "number": 4518},
        }

        changes = adapter.diff(previous, current)

        self.assertEqual([item["id"] for item in changes["review_comments"]], [12, 13])
        self.assertEqual([item["id"] for item in changes["created"]], [12])
        self.assertEqual([item["id"] for item in changes["updated"]], [13])

    def test_diff_records_new_source_errors_once(self):
        adapter = GitHubPRAdapter()
        previous = {"items": [], "meta": {"repo": "lusipad/KAM", "watch": "review_comments", "number": 4518}}
        current = {
            "items": [],
            "meta": {
                "repo": "lusipad/KAM",
                "watch": "review_comments",
                "number": 4518,
                "error": "HTTP404Error: 404 Not Found",
            },
        }

        changes = adapter.diff(previous, current)

        self.assertEqual(len(changes["errors"]), 1)
        self.assertEqual(changes["errors"][0]["number"], 4518)
        self.assertIn("404", changes["errors"][0]["message"])

        repeated = adapter.diff(current, current)
        self.assertEqual(repeated["errors"], [])

    def test_recommended_actions_include_pr_context_and_comment_details(self):
        adapter = GitHubPRAdapter()
        changes = {
            "review_comments": [
                {
                    "id": 99,
                    "body": "Please reuse the existing helper instead of re-implementing this branch.",
                    "path": "backend/services/run_engine.py",
                    "line": 42,
                    "user": "reviewer",
                    "html_url": "https://github.com/lusipad/KAM/pull/4518#discussion_r1",
                }
            ],
            "meta": {"repo": "lusipad/KAM", "number": 4518},
        }

        actions = adapter.recommended_actions(
            {"name": "PR #4518 评审监控", "config": {"repo": "lusipad/KAM", "number": 4518}},
            changes,
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["kind"], "create_run")
        task = actions[0]["params"]["task"]
        self.assertIn("lusipad/KAM PR #4518", task)
        self.assertIn("新发现的评审评论", task)
        self.assertIn("run_engine.py", task)
        self.assertIn("discussion_r1", task)


if __name__ == "__main__":
    unittest.main()
