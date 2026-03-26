"""
KAM v2 线程与消息服务
"""
from __future__ import annotations

import re
import threading
from typing import Any

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.core.time import utc_now
from app.db.base import SessionLocal
from app.models.conversation import Message, Thread
from app.models.project import Project, ProjectResource
from app.services.anthropic_service import AnthropicService


URL_PATTERN = re.compile(r"""https?://[^\s<>"'）)\]]+""")
PATH_PATTERN = re.compile(r"(?<!://)(?<![A-Za-z0-9])(?:\.{1,2}/|/)?(?:[A-Za-z0-9_.-]+/){1,}[A-Za-z0-9_.-]+/?")
TRAILING_PUNCTUATION = ",.;:!?)，。；：！？】》）」』'\""


class ThreadService:
    def __init__(self, db: Session):
        self.db = db
        self.anthropic = AnthropicService()

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
        project.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(thread)
        return thread

    def get_thread(self, thread_id: str) -> Thread | None:
        return self.db.query(Thread).filter(Thread.id == thread_id).first()

    def create_message(self, thread_id: str, data: dict[str, Any]) -> Message | None:
        thread = self.get_thread(thread_id)
        if not thread:
            return None

        had_messages = bool(thread.messages)
        message_role = data.get("role", "user")
        should_generate_title = (
            not had_messages
            and message_role == "user"
            and (thread.title or "新对话") == "新对话"
        )
        message = Message(
            thread_id=thread.id,
            role=message_role,
            content=data["content"],
            metadata_=data.get("metadata") or {},
        )
        self.db.add(message)
        self.db.flush()

        if should_generate_title:
            normalized = message.content.strip().replace("\n", " ")
            if normalized:
                thread.title = normalized[:40]

        extracted_count = 0
        if message.role == "user" and thread.project_id:
            extracted_count = self._auto_extract_resources(
                project_id=str(thread.project_id),
                thread_id=str(thread.id),
                message_id=str(message.id),
                content=message.content,
            )
            if extracted_count:
                message.metadata_ = {
                    **(message.metadata_ or {}),
                    "autoExtractedResourceCount": extracted_count,
                }

        thread.updated_at = utc_now()
        if thread.project:
            thread.project.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(message)
        event_bus.publish(
            f"thread:{thread_id}",
            {
                "type": "thread-updated",
                "threadId": thread_id,
                "messageId": str(message.id),
                "role": message.role,
            },
        )
        if should_generate_title:
            self._schedule_thread_title(str(thread.id), message.content)
        return message

    def _schedule_thread_title(self, thread_id: str, first_message: str):
        worker = threading.Thread(
            target=self._update_thread_title,
            args=(thread_id, first_message),
            daemon=True,
        )
        worker.start()

    def _update_thread_title(self, thread_id: str, first_message: str):
        db = SessionLocal()
        try:
            thread = db.query(Thread).filter(Thread.id == thread_id).first()
            if not thread:
                return
            title = self._generate_thread_title(first_message)
            if not title:
                return
            thread.title = title
            thread.updated_at = utc_now()
            db.commit()
            event_bus.publish(
                f"thread:{thread_id}",
                {
                    "type": "thread-updated",
                    "threadId": thread_id,
                },
            )
        finally:
            db.close()

    def _generate_thread_title(self, first_message: str) -> str:
        normalized = " ".join(first_message.strip().split())
        if not normalized:
            return "新对话"
        if self.anthropic.enabled:
            title = self.anthropic.generate_text_sync(
                system="用不超过 10 个汉字概括这个工作，只输出标题。",
                messages=[{"role": "user", "content": normalized[:240]}],
                max_tokens=32,
            )
            title = title.strip().strip('"').strip("《》[]【】")
            if title:
                return title[:10]
        return normalized[:10]

    def _auto_extract_resources(self, *, project_id: str, thread_id: str, message_id: str, content: str) -> int:
        created = 0
        for resource in self._iter_message_resources(content):
            exists = (
                self.db.query(ProjectResource)
                .filter(ProjectResource.project_id == project_id, ProjectResource.uri == resource["uri"])
                .first()
            )
            if exists:
                continue
            self.db.add(
                ProjectResource(
                    project_id=project_id,
                    resource_type=resource["type"],
                    title=resource.get("title"),
                    uri=resource["uri"],
                    pinned=False,
                    metadata_={
                        "autoExtracted": True,
                        "sourceThreadId": thread_id,
                        "sourceMessageId": message_id,
                        "detectedType": resource["type"],
                    },
                )
            )
            created += 1
        return created

    def _iter_message_resources(self, content: str):
        seen: set[str] = set()

        for match in URL_PATTERN.findall(content):
            uri = match.rstrip(TRAILING_PUNCTUATION)
            if not uri or uri in seen:
                continue
            seen.add(uri)
            title = uri.rstrip('/').split('/')[-1] or uri
            yield {
                "type": "url",
                "title": title[:200],
                "uri": uri,
            }

        for match in PATH_PATTERN.finditer(content):
            raw_value = match.group(0).strip().rstrip(TRAILING_PUNCTUATION)
            if not raw_value or raw_value in seen or "://" in raw_value:
                continue

            normalized = raw_value
            if normalized.endswith('/') and normalized != '/':
                normalized = normalized.rstrip('/')
            if normalized.count('/') < 1:
                continue
            if self._looks_like_numeric_path(normalized):
                continue

            basename = normalized.split('/')[-1]
            resource_type = "file" if "." in basename else "repo-path"
            if normalized in seen:
                continue
            seen.add(normalized)
            yield {
                "type": resource_type,
                "title": basename[:200] or normalized[:200],
                "uri": normalized,
            }

    def _looks_like_numeric_path(self, value: str) -> bool:
        segments = [segment for segment in value.strip('/').split('/') if segment not in {".", "..", ""}]
        return bool(segments) and all(segment.isdigit() for segment in segments)
