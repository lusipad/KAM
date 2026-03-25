"""
数据库基础配置
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings
from app.db.types import IS_SQLITE


if IS_SQLITE:
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)

engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "echo": settings.APP_DEBUG,
}

if IS_SQLITE:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

from app import models as _models  # noqa: E402,F401


EXPECTED_V2_COLUMNS = {
    "projects": {"id", "title", "status", "repo_path", "description", "check_commands", "settings", "created_at", "updated_at"},
    "threads": {"id", "project_id", "title", "status", "created_at", "updated_at"},
    "messages": {"id", "thread_id", "role", "content", "metadata", "created_at"},
    "runs": {"id", "thread_id", "message_id", "agent", "model", "reasoning_effort", "command", "status", "work_dir", "round", "max_rounds", "duration_ms", "error", "metadata", "created_at", "completed_at"},
    "thread_run_artifacts": {"id", "run_id", "artifact_type", "title", "content", "path", "round", "metadata", "created_at"},
    "project_resources": {"id", "project_id", "resource_type", "title", "uri", "pinned", "metadata", "created_at"},
    "user_preferences": {"id", "category", "key", "value", "embedding", "source_thread_id", "created_at"},
    "decision_log": {"id", "project_id", "question", "decision", "reasoning", "embedding", "source_thread_id", "created_at"},
    "project_learnings": {"id", "project_id", "content", "embedding", "source_thread_id", "created_at"},
}

ADDITIVE_V2_COLUMNS = {
    "user_preferences": {"embedding": "JSON"},
    "decision_log": {"embedding": "JSON"},
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    _ensure_additive_v2_columns()
    _repair_incompatible_v2_tables()
    Base.metadata.create_all(bind=engine)


def _ensure_additive_v2_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table_name, columns in ADDITIVE_V2_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            current_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name in current_columns:
                    continue
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'))


def _repair_incompatible_v2_tables() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    incompatible_tables: list[str] = []

    for table_name, expected_columns in EXPECTED_V2_COLUMNS.items():
        if table_name not in existing_tables:
            continue
        current_columns = {column["name"] for column in inspector.get_columns(table_name)}
        if not expected_columns.issubset(current_columns):
            incompatible_tables.append(table_name)

    if not incompatible_tables:
        return

    if IS_SQLITE and settings.DATABASE_URL.startswith("sqlite:///"):
        _backup_sqlite_database()
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            for table_name in incompatible_tables:
                backup_table = f"legacy_{table_name}_backup_{timestamp}"
                conn.execute(text(f'CREATE TABLE IF NOT EXISTS "{backup_table}" AS SELECT * FROM "{table_name}"'))
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
            conn.execute(text("PRAGMA foreign_keys=ON"))
        return

    with engine.begin() as conn:
        for table_name in incompatible_tables:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))


def _backup_sqlite_database() -> None:
    db_path = Path(settings.DATABASE_URL.replace("sqlite:///", "", 1))
    if not db_path.exists():
        return
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_path = db_path.with_suffix(db_path.suffix + f".v2-init-backup-{timestamp}")
    engine.dispose()
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, backup_path)
