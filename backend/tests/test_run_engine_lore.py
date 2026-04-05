from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models import Task, TaskRun  # noqa: E402
from services.run_engine import RunEngine  # noqa: E402


class RunEngineLoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="kam-run-engine-"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_commit_message_uses_lore_trailers(self):
        task = Task(
            id="task123",
            title="Stabilize task-first harness",
            repo_path="D:/Repos/KAM",
            status="open",
            priority="high",
            labels=[],
        )
        run = TaskRun(
            id="run123",
            task_id=task.id,
            agent="codex",
            status="passed",
            task="Lock the commit shape for harness-generated changes",
        )

        message = RunEngine(None)._build_commit_message(run, task)

        self.assertTrue(message.startswith("Advance Stabilize task-first harness through a codex harness run"))
        self.assertIn("Constraint:", message)
        self.assertIn("Confidence:", message)
        self.assertIn("Scope-risk:", message)
        self.assertIn("Reversibility:", message)
        self.assertIn("Directive:", message)
        self.assertIn("Tested:", message)
        self.assertIn("Not-tested:", message)
        self.assertIn("Related: task/task123", message)
        self.assertIn("Related: run/run123", message)

    def test_finalize_success_commits_with_lore_message(self):
        repo = self.temp_dir / "repo"
        repo.mkdir(parents=True)
        self._git(repo, "init")
        self._git(repo, "config", "user.name", "Test User")
        self._git(repo, "config", "user.email", "test@example.com")

        file_path = repo / "README.md"
        file_path.write_text("before\n", encoding="utf-8")
        self._git(repo, "add", "README.md")
        self._git(repo, "commit", "-m", "Initial commit")

        file_path.write_text("after\n", encoding="utf-8")

        task = Task(
            id="task456",
            title="Make harness commits self-describing",
            repo_path=str(repo),
            status="in_progress",
            priority="high",
            labels=[],
        )
        run = TaskRun(
            id="run456",
            task_id=task.id,
            agent="codex",
            status="running",
            task="Replace single-line auto commit messages with Lore protocol content",
        )

        result = asyncio.run(RunEngine(None)._finalize_success(run, task, repo, repo))
        message = self._git_output(repo, "log", "-1", "--pretty=%B")

        self.assertEqual(result.changed_files, ["README.md"])
        self.assertIn("README.md", result.patch_output)
        self.assertIn("Advance Make harness commits self-describing through a codex harness run", message)
        self.assertIn("Constraint:", message)
        self.assertIn("Directive:", message)
        self.assertIn("Related: task/task456", message)

    def _git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _git_output(self, cwd: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout


if __name__ == "__main__":
    unittest.main()
