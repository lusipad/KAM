"""
破坏式重置数据库，只保留 KAM Lite Core 所需表。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.base import Base, engine
from app.db.types import IS_SQLITE
from app.models import workspace  # noqa: F401

LITE_TABLES = [
    "run_artifacts",
    "agent_runs",
    "context_snapshots",
    "task_refs",
    "task_cards",
]


def reset_sqlite() -> None:
    engine.dispose()
    db_path = settings.DATABASE_URL.replace("sqlite:///", "", 1)
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()

    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def reset_postgres() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = [
            table_name
            for table_name in inspector.get_table_names()
            if not table_name.startswith("pg_")
        ]
        for table_name in table_names:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))

    Base.metadata.create_all(bind=engine)


def main() -> None:
    if IS_SQLITE:
        reset_sqlite()
    else:
        reset_postgres()

    print("Lite Core schema reset complete.")
    print(f"DATABASE_URL={settings.DATABASE_URL}")
    print("Tables: task_cards, task_refs, context_snapshots, agent_runs, run_artifacts")


if __name__ == "__main__":
    main()
