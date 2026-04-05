from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.agent_readiness import check_agent_readiness


class AgentReadinessTests(unittest.TestCase):
    def test_codex_uses_login_status_command(self):
        with (
            patch("backend.scripts.agent_readiness.settings.codex_path", new="codex"),
            patch("backend.scripts.agent_readiness._resolve_binary", return_value="codex.cmd"),
            patch(
                "backend.scripts.agent_readiness.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=["codex.cmd", "login", "status"],
                    returncode=0,
                    stdout="ok",
                    stderr="",
                ),
            ) as run_mock,
        ):
            result = check_agent_readiness("codex")

        self.assertTrue(result.ok)
        self.assertEqual(result.binary, "codex.cmd")
        self.assertEqual(result.command, ["codex.cmd", "login", "status"])
        run_mock.assert_called_once()

    def test_claude_code_uses_auth_status_command(self):
        with (
            patch("backend.scripts.agent_readiness.settings.claude_code_path", new="C:/Users/test/claude.cmd"),
            patch("backend.scripts.agent_readiness._resolve_binary", return_value="C:/Users/test/claude.cmd"),
            patch(
                "backend.scripts.agent_readiness.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=["C:/Users/test/claude.cmd", "auth", "status"],
                    returncode=1,
                    stdout='{"loggedIn": false}',
                    stderr="",
                ),
            ),
        ):
            result = check_agent_readiness("claude-code")

        self.assertFalse(result.ok)
        self.assertEqual(result.command, ["C:/Users/test/claude.cmd", "auth", "status"])
        self.assertIn("claude-code 登录态", result.message)
        self.assertEqual(result.detail, '{"loggedIn": false}')

    def test_missing_binary_returns_skip_hint(self):
        missing_binary = str(Path("C:/missing/claude.cmd"))
        with (
            patch("backend.scripts.agent_readiness.settings.claude_code_path", new=missing_binary),
            patch("backend.scripts.agent_readiness._resolve_binary", return_value=missing_binary),
            patch("backend.scripts.agent_readiness.subprocess.run", side_effect=FileNotFoundError()),
        ):
            result = check_agent_readiness("claude-code")

        self.assertFalse(result.ok)
        self.assertIn("-SkipRealAgentSmoke", result.message)
        self.assertEqual(result.detail, f"missing binary: {missing_binary}")


if __name__ == "__main__":
    unittest.main()
