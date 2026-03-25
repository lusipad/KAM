"""
KAM v2 线程与消息服务
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.conversation import Message, Thread
from app.models.project import Project


class ThreadService:
    def __init__(self, db: Session):
        self.db = db

    def list_threads(self, project_id: str, status: str | None = None) -> list[Thread]:
        query = self.db.query(Thread).filter(Thread.project_id == project_id)
        if status:
            query = query.filter(Thread.status == status)
        return query.order_by(Thread.updated_at.desc()).all()

    def create_thread(self, project_id: str, data: dict[str, Any]) -> Thread | None:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        title = (data.get("title") or "").strip() or "新对话"
        thread = Thread(
            project_id=project.id,
            title=title,
            status=data.get("status", "active"),
        )
        self.db.add(thread)
        project.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(thread)
        return thread

    def get_thread(self, thread_id: str) -> Thread | None:
        return self.db.query(Thread).filter(Thread.id == thread_id).first()

    def create_message(self, thread_id: str, data: dict[str, Any]) -> Message | None:
        thread = self.get_thread(thread_id)
        if not thread:
            return None

        message = Message(
            thread_id=thread.id,
            role=data.get("role", "user"),
            content=data["content"],
            metadata_=data.get("metadata") or {},
        )
        self.db.add(message)
        if len(thread.messages or []) == 0 and (thread.title or "新对话") == "新对话" and message.role == "user":
            normalized = message.content.strip().replace("\n", " ")
            if normalized:
                thread.title = normalized[:40]
        thread.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(message)
        return message
