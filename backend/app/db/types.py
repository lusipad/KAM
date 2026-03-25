"""
数据库类型兼容层
"""
from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from app.core.config import settings


IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")
IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")


def uuid_type():
    if IS_SQLITE:
        return String(36)
    return PostgresUUID(as_uuid=True)


def uuid_default():
    if IS_SQLITE:
        return str(uuid.uuid4())
    return uuid.uuid4()
