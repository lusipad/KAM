from __future__ import annotations

import json
import re
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Message, Thread, now
from services.context import ContextAssembler
from services.memory import MemoryService
from services.run_engine import RunEngine
from services.watcher import watcher_engine


class ConversationRouter:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def route_message(self, *, thread_id: str, message_content: str, project_id: str | None) -> list[dict[str, Any]]:
        context = await ContextAssembler(self.db).build(thread_id=thread_id, project_id=project_id, query=message_content)
        decision = await self._decide(message_content, context)
        events: list[dict[str, Any]] = []

        memory_service = MemoryService(self.db)
        for memory_payload in decision.get("memories", []):
            memory = await memory_service.record(
                project_id=project_id,
                category=memory_payload["category"],
                content=memory_payload["content"],
                rationale=memory_payload.get("rationale"),
                source_thread_id=thread_id,
            )
            events.append({"type": "tool_result", "tool": "record_memory", "memory": memory.to_dict()})

        watcher_payload = decision.get("watcher")
        if watcher_payload:
            watcher = await watcher_engine.create_watcher(
                self.db,
                project_id=project_id,
                name=watcher_payload["name"],
                source_type=watcher_payload["sourceType"],
                config=watcher_payload["config"],
                schedule_type=watcher_payload["scheduleType"],
                schedule_value=watcher_payload["scheduleValue"],
                auto_action_level=watcher_payload.get("autoActionLevel", 1),
            )
            self.db.add(
                Message(
                    thread_id=thread_id,
                    role="system",
                    content=f"Configured watcher {watcher.name}.",
                    metadata_={"kind": "watcher-config", "watcher": watcher.to_dict()},
                )
            )
            events.append({"type": "tool_result", "tool": "create_watcher", "watcher": watcher.to_dict()})

        run_payload = decision.get("run")
        if run_payload:
            run = await RunEngine(self.db).create_run(
                thread_id=thread_id,
                agent=run_payload["agent"],
                task=run_payload["task"],
            )
            events.append({"type": "tool_result", "tool": "create_run", "run": run.to_dict()})

        reply = decision.get("assistantReply", "收到。")
        await self._touch_thread(thread_id)
        for fragment in self._stream_text(reply):
            events.append({"type": "text_delta", "delta": fragment})
        events.append({"type": "text_done", "content": reply})
        return events

    async def _touch_thread(self, thread_id: str) -> None:
        thread = await self.db.get(Thread, thread_id)
        if thread is not None:
            thread.updated_at = now()
            await self.db.commit()

    async def _decide(self, message_content: str, context: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            return self._fallback_decision(message_content)

        prompt = (
            "You are the KAM orchestration core. Return strict JSON with keys "
            "assistantReply, run, watcher, memories. Keep assistantReply concise. "
            "run or watcher may be null. memories is an array.\n\n"
            f"{context['project_block']}\n\n{context['memory_block']}\n\n{context['recent_context']}\n\n"
            f"User: {message_content}"
        )
        fallback = self._fallback_decision(message_content)
        try:
            response = await self.client.messages.create(
                model=settings.chat_model,
                max_tokens=600,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            return fallback

        text = "".join(getattr(block, "text", "") for block in response.content).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return fallback
        parsed.setdefault("assistantReply", fallback["assistantReply"])
        parsed.setdefault("memories", [])
        return parsed

    def _fallback_decision(self, message_content: str) -> dict[str, Any]:
        text = message_content.strip()
        lower = text.lower()

        memories = []
        if any(token in lower for token in {"always", "never", "prefer", "偏好", "以后都", "不要"}):
            memories.append(
                {
                    "category": "preference",
                    "content": text,
                    "rationale": "Captured from direct user preference.",
                }
            )

        watcher = None
        if any(token in lower for token in {"watch", "monitor", "watcher", "监控", "订阅"}):
            source_type = "github_pr"
            if "azure" in lower or "devops" in lower:
                source_type = "azure_devops"
            elif "ci" in lower or "workflow" in lower:
                source_type = "ci_pipeline"
            watcher = {
                "name": self._title_from(text, prefix="Watcher"),
                "sourceType": source_type,
                "config": self._watcher_config_from(text, source_type),
                "scheduleType": "interval",
                "scheduleValue": "15m",
                "autoActionLevel": 1,
            }

        run = None
        if any(
            token in lower
            for token in {
                "fix",
                "implement",
                "build",
                "debug",
                "refactor",
                "deploy",
                "review",
                "修复",
                "实现",
                "重构",
                "部署",
                "检查",
            }
        ):
            run = {"agent": "codex", "task": text}

        if watcher:
            reply = "我已经把这件事整理成 watcher 配置，激活后会在 Home feed 持续推送。"
        elif run:
            reply = "我先起一个执行任务，结果会直接折回这个线程。"
        elif memories:
            reply = "我记住这个偏好了，后续会按这个方式工作。"
        else:
            reply = "收到。你继续描述目标，我会把需要执行的部分转成后台任务。"

        return {"assistantReply": reply, "run": run, "watcher": watcher, "memories": memories}

    def _watcher_config_from(self, text: str, source_type: str) -> dict[str, Any]:
        repo_match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text)
        repo = repo_match.group(1) if repo_match else "owner/repo"
        if source_type == "azure_devops":
            return {"project": "KAM", "watch": "assigned_work_items"}
        if source_type == "ci_pipeline":
            return {"repo": repo, "provider": "github_actions", "branch": "main"}
        number_match = re.search(r"#(\d+)", text)
        if number_match:
            return {"repo": repo, "watch": "review_comments", "number": int(number_match.group(1))}
        return {"repo": repo, "watch": "assigned_prs", "filter_user": "me"}

    def _title_from(self, text: str, prefix: str) -> str:
        compact = " ".join(text.split())
        return f"{prefix}: {compact[:96]}"

    def _stream_text(self, content: str) -> list[str]:
        if len(content) <= 32:
            return [content]
        segments = []
        cursor = 0
        while cursor < len(content):
            segments.append(content[cursor : cursor + 24])
            cursor += 24
        return segments
