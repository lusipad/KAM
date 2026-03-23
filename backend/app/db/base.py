"""
数据库基础配置
"""
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings
from app.db.types import IS_POSTGRES, IS_SQLITE


if IS_SQLITE:
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)

engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "echo": settings.APP_DEBUG,
}

if IS_SQLITE:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

# 创建引擎
engine = create_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库 - 创建所有表"""
    # 导入所有模型以确保它们被注册
    from app.models import note, link, memory, agent, task, ado_config, conversation
    
    # 创建表
    Base.metadata.create_all(bind=engine)
    
    # 启用pgvector扩展
    if IS_POSTGRES:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
