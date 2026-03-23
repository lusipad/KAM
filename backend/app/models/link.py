"""
链接模型 (双向链接)
"""
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class Link(Base):
    __tablename__ = "links"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    source_note_id = Column(uuid_type(), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    target_note_id = Column(uuid_type(), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(String(20), default="wiki")  # wiki, tag, block, embed, external
    context = Column(JSON, default=dict)
    is_resolved = Column(Boolean, default=True)
    is_embed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # 关系
    source_note = relationship("Note", foreign_keys=[source_note_id], backref="outgoing_links")
    target_note = relationship("Note", foreign_keys=[target_note_id], backref="incoming_links")
    
    __table_args__ = (
        Index('idx_links_source', 'source_note_id'),
        Index('idx_links_target', 'target_note_id'),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "sourceNoteId": str(self.source_note_id),
            "targetNoteId": str(self.target_note_id),
            "type": self.link_type,
            "context": self.context or {},
            "isResolved": self.is_resolved,
            "isEmbed": self.is_embed,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
