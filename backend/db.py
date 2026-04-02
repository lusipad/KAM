from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings
from models import Base


connect_args: dict[str, object] = {}
engine_kwargs: dict[str, object] = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    if settings.is_test_env:
        engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, echo=settings.app_debug, connect_args=connect_args, **engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


async def init_db() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.run_dir.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
