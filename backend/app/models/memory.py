"""
长期记忆模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON, Index, Float, Integer

from app.db.base import Base
from app.db.types import IS_POSTGRES, vector_type, uuid_default, uuid_type


class Memory(Base):
    __tablename__ = "memories"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    user_id = Column(String(100), default="default")
    memory_type = Column(String(20), nullable=False)  # fact, procedure, episodic
    category = Column(String(100))
    content = Column(Text, nullable=False)
    content_vector = Column(vector_type(3072))  # text-embedding-3-large dimension
    summary = Column(Text)
    summary_vector = Column(vector_type(3072))
    importance_score = Column(Float, default=0.5)
    confidence_score = Column(Float, default=0.8)
    access_count = Column(Integer, default=0)
    metadata_ = Column("metadata", JSON, default=dict)
    context = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    last_accessed = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    _table_args = [
        Index('idx_memories_user', 'user_id'),
        Index('idx_memories_type', 'memory_type'),
        Index('idx_memories_importance', 'importance_score'),
    ]

    if IS_POSTGRES:
        _table_args.append(
            Index(
                'idx_memories_vector',
                content_vector,
                postgresql_using='ivfflat',
                postgresql_with={'lists': 100},
                postgresql_ops={'content_vector': 'vector_cosine_ops'},
            )
        )

    __table_args__ = tuple(_table_args)
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "userId": self.user_id,
            "memoryType": self.memory_type,
            "category": self.category,
            "content": self.content,
            "summary": self.summary,
            "importanceScore": self.importance_score,
            "confidenceScore": self.confidence_score,
            "accessCount": self.access_count,
            "metadata": self.metadata_ or {},
            "context": self.context or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "lastAccessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }
