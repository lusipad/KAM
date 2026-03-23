"""
对话模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    title = Column(String(500), default="新对话")
    context = Column(JSON, default=dict)  # 存储关联的noteIds, memoryIds等
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "context": self.context or {},
            "messages": [m.to_dict() for m in self.messages] if self.messages else [],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    conversation_id = Column(uuid_type(), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)  # model, tokens, latency等
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # 关系
    conversation = relationship("Conversation", back_populates="messages")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "conversationId": str(self.conversation_id),
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata_ or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
