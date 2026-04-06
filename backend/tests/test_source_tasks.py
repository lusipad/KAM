from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch


TMP_ROOT = Path(tempfile.mkdtemp(prefix="kam-source-task-tests-"))
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["STORAGE_PATH"] = str(TMP_ROOT)
os.environ["APP_ENV"] = "test"

from services import source_tasks  # noqa: E402


class SourceTaskLockTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(TMP_ROOT / "source-task-locks", ignore_errors=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_waits_until_existing_lock_can_turn_stale(self):
        dedup_key = "github_pr_review_comments:lusipad/KAM:4518"
        lock_path = source_tasks._source_task_lock_path(dedup_key)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            json.dumps(
                {
                    "ownerId": "stale-owner",
                    "dedupKey": dedup_key,
                    "acquiredAt": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        async def scenario() -> None:
            with (
                patch.object(source_tasks, "_SOURCE_TASK_LOCK_TTL_SECONDS", 0.12),
                patch.object(source_tasks, "_SOURCE_TASK_LOCK_WAIT_SECONDS", 0.05),
                patch.object(source_tasks, "_SOURCE_TASK_LOCK_POLL_SECONDS", 0.01),
            ):
                started = time.perf_counter()
                async with source_tasks.source_task_guard(dedup_key):
                    elapsed = time.perf_counter() - started
                    self.assertGreaterEqual(elapsed, 0.1)
                    payload = json.loads(lock_path.read_text(encoding="utf-8"))
                    self.assertEqual(payload["dedupKey"], dedup_key)
                    self.assertNotEqual(payload["ownerId"], "stale-owner")

        asyncio.run(scenario())
        self.assertFalse(lock_path.exists())

    def test_waits_until_recent_corrupt_lock_can_turn_stale(self):
        dedup_key = "github_pr_review_comments:lusipad/KAM:4519"
        lock_path = source_tasks._source_task_lock_path(dedup_key)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("{not-json", encoding="utf-8")

        async def scenario() -> None:
            with (
                patch.object(source_tasks, "_SOURCE_TASK_LOCK_TTL_SECONDS", 0.12),
                patch.object(source_tasks, "_SOURCE_TASK_LOCK_WAIT_SECONDS", 0.05),
                patch.object(source_tasks, "_SOURCE_TASK_LOCK_POLL_SECONDS", 0.01),
            ):
                started = time.perf_counter()
                async with source_tasks.source_task_guard(dedup_key):
                    elapsed = time.perf_counter() - started
                    self.assertGreaterEqual(elapsed, 0.1)
                    payload = json.loads(lock_path.read_text(encoding="utf-8"))
                    self.assertEqual(payload["dedupKey"], dedup_key)

        asyncio.run(scenario())
        self.assertFalse(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
