"""
数据库基础配置
"""
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import workspace  # noqa: F401

    Base.metadata.create_all(bind=engine)
