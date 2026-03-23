"""
数据库类型兼容层
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from app.core.config import settings


IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")
IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")


def uuid_type():
    """为当前数据库返回兼容的 UUID 列类型。"""
    if IS_SQLITE:
        return String(36)
    return PostgresUUID(as_uuid=True)


def uuid_default():
    """根据后端数据库返回兼容的 UUID 默认值。"""
    if IS_SQLITE:
        return str(uuid.uuid4())
    return uuid.uuid4()


def vector_type(dimension: int):
    """
    pgvector 在 SQLite 本地开发场景下不可用，降级为 JSON 存储。
    """
    if IS_SQLITE:
        return JSON

    from pgvector.sqlalchemy import Vector

    return Vector(dimension)
