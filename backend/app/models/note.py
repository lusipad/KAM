"""
笔记模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON, Index

from app.db.base import Base
from app.db.types import vector_type, uuid_default, uuid_type


class Note(Base):
    __tablename__ = "notes"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    title = Column(String(500), nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    content_type = Column(String(20), default="markdown")
    path = Column(String(1000), nullable=False)
    version = Column(Integer, default=1)
    metadata_ = Column("metadata", JSON, default=dict)
    stats = Column(JSON, default=dict)
    content_vector = Column(vector_type(3072))  # text-embedding-3-large dimension
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 全文搜索索引
    __table_args__ = (
        Index('idx_notes_fts', 'title', 'content', postgresql_using='gin'),
        Index('idx_notes_updated', 'updated_at'),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "content": self.content,
            "contentType": self.content_type,
            "path": self.path,
            "version": self.version,
            "metadata": self.metadata_ or {},
            "stats": self.stats or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
