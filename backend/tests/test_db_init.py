from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


TMP_ROOT = Path(tempfile.mkdtemp(prefix="kam-db-init-tests-"))
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP_ROOT / 'kam-init-bootstrap.db').as_posix()}"
os.environ["STORAGE_PATH"] = str(TMP_ROOT)
os.environ["RUN_ROOT"] = str(TMP_ROOT / "runs")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["APP_ENV"] = "test"

from config import settings  # noqa: E402
from db import _sync_database_url, init_db  # noqa: E402
from models import Base  # noqa: E402


class InitDbTests(unittest.TestCase):
    def setUp(self):
        self.database_path = TMP_ROOT / f"{self._testMethodName}.db"
        if self.database_path.exists():
            self.database_path.unlink()
        self.database_url = f"sqlite+aiosqlite:///{self.database_path.as_posix()}"
        settings.database_url = self.database_url

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_init_db_creates_fresh_database_at_head(self):
        asyncio.run(init_db())

        with create_engine(_sync_database_url(self.database_url)).connect() as connection:
            tables = set(inspect(connection).get_table_names())
            self.assertIn("tasks", tables)
            self.assertIn("task_runs", tables)
            self.assertNotIn("projects", tables)
            self.assertNotIn("runs", tables)
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            self.assertEqual(version, self._head_revision())

    def test_init_db_stamps_existing_create_all_database_to_head(self):
        sync_engine = create_engine(_sync_database_url(self.database_url))
        try:
            Base.metadata.create_all(sync_engine)
        finally:
            sync_engine.dispose()

        asyncio.run(init_db())

        with create_engine(_sync_database_url(self.database_url)).connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            self.assertEqual(version, self._head_revision())
            self.assertIn("task_runs", inspect(connection).get_table_names())
            self.assertNotIn("projects", inspect(connection).get_table_names())

    def _head_revision(self):
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        return ScriptDirectory.from_config(config).get_current_head()
