"""
重置数据库为 v1 Lite Core 旧 schema，供 Phase 1 迁移验证使用。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.base import engine
from app.db.types import IS_SQLITE
from scripts.legacy_schema import LEGACY_TABLE_NAMES, create_legacy_tables


def reset_sqlite() -> None:
    engine.dispose()
    db_path = settings.DATABASE_URL.replace('sqlite:///', '', 1)
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    create_legacy_tables(engine)


def reset_postgres() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = [table_name for table_name in inspector.get_table_names() if not table_name.startswith('pg_')]
        for table_name in table_names:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
    create_legacy_tables(engine)


def main() -> None:
    if IS_SQLITE:
        reset_sqlite()
    else:
        reset_postgres()
    print('Lite Core legacy schema reset complete.')
    print(f'DATABASE_URL={settings.DATABASE_URL}')
    print('Tables: ' + ', '.join(LEGACY_TABLE_NAMES))


if __name__ == '__main__':
    main()
