from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy import text as sql_text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings


connect_args: dict[str, object] = {}
engine_kwargs: dict[str, object] = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    if settings.is_test_env:
        engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, echo=settings.app_debug, connect_args=connect_args, **engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
BACKEND_ROOT = Path(__file__).resolve().parent
ALEMBIC_INI_PATH = BACKEND_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = BACKEND_ROOT / "alembic"
LEGACY_BASE_REVISION = "001_v3_initial"
TASK_FIRST_BASE_REVISION = "002_task_harness_schema"
KNOWN_APP_TABLES = {
    "projects",
    "threads",
    "messages",
    "runs",
    "run_artifacts",
    "memories",
    "watchers",
    "watcher_events",
    "tasks",
    "task_refs",
    "context_snapshots",
    "task_runs",
    "task_run_artifacts",
    "review_compares",
}
TASK_FIRST_TABLES = {
    "tasks",
    "task_refs",
    "context_snapshots",
    "task_runs",
    "task_run_artifacts",
    "review_compares",
}


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


def _database_file_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return None
    if not url.database or url.database == ":memory:":
        return None
    return Path(url.database).resolve()


def _build_alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    return config


def _sync_database_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername == "sqlite+aiosqlite":
        url = url.set(drivername="sqlite")
    elif url.drivername == "postgresql+asyncpg":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def _bootstrap_existing_schema(config: Config) -> bool:
    connectable = create_engine(_sync_database_url(settings.database_url))
    try:
        with connectable.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            revision = None
            if "alembic_version" in tables:
                revision = connection.execute(sql_text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    finally:
        connectable.dispose()

    current_head = ScriptDirectory.from_config(config).get_current_head()
    if revision == current_head:
        return True
    if revision is not None or not tables.intersection(KNOWN_APP_TABLES):
        return False

    base_revision = TASK_FIRST_BASE_REVISION if tables.intersection(TASK_FIRST_TABLES) else LEGACY_BASE_REVISION
    command.stamp(config, base_revision)
    return False


def _run_migrations() -> None:
    config = _build_alembic_config()
    if _bootstrap_existing_schema(config):
        return
    command.upgrade(config, "head")


async def init_db() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.run_dir.mkdir(parents=True, exist_ok=True)
    database_file = _database_file_path(settings.database_url)
    if database_file is not None:
        database_file.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_run_migrations)
