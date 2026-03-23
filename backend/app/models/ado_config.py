"""
Azure DevOps配置模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, JSON

from app.db.base import Base
from app.db.types import uuid_default, uuid_type


class ADOConfig(Base):
    __tablename__ = "ado_configs"
    
    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    name = Column(String(200), nullable=False)
    server_url = Column(String(500), nullable=False)
    collection = Column(String(200), default="DefaultCollection")
    project = Column(String(200), nullable=False)
    auth_type = Column(String(20), default="pat")  # pat, oauth, ntlm
    credentials = Column(JSON, default=dict)  # 加密存储
    scopes = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self, include_credentials: bool = False):
        data = {
            "id": str(self.id),
            "name": self.name,
            "serverUrl": self.server_url,
            "collection": self.collection,
            "project": self.project,
            "authType": self.auth_type,
            "scopes": self.scopes or [],
            "isActive": self.is_active,
            "lastSyncAt": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_credentials:
            data["credentials"] = self.credentials
        return data
