"""
Anthropic SDK 轻量封装。
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings

try:
    from anthropic import Anthropic, AsyncAnthropic
except Exception:  # pragma: no cover - 依赖缺失时退化到无 LLM
    Anthropic = None
    AsyncAnthropic = None


def anthropic_available() -> bool:
    return bool(settings.ANTHROPIC_API_KEY.strip() and Anthropic is not None and AsyncAnthropic is not None)


def extract_text_from_message(message: Any) -> str:
    chunks: list[str] = []
    for block in getattr(message, "content", None) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", "") or ""
            if text:
                chunks.append(text)
            continue
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "")
            if text:
                chunks.append(text)
    return "".join(chunks).strip()


def iter_tool_uses(message: Any):
    for block in getattr(message, "content", None) or []:
        block_type = getattr(block, "type", None)
        if block_type == "tool_use":
            yield {
                "name": getattr(block, "name", "") or "",
                "input": getattr(block, "input", None) or {},
                "id": getattr(block, "id", None),
            }
            continue
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield {
                "name": str(block.get("name") or ""),
                "input": block.get("input") or {},
                "id": block.get("id"),
            }


class AnthropicService:
    def __init__(self):
        self._api_key = settings.ANTHROPIC_API_KEY.strip()

    @property
    def enabled(self) -> bool:
        return anthropic_available()

    def create_sync_client(self):
        if not self.enabled:
            return None
        return Anthropic(api_key=self._api_key, max_retries=1)

    def create_async_client(self):
        if not self.enabled:
            return None
        return AsyncAnthropic(api_key=self._api_key, max_retries=1)

    async def generate_text(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 768,
        model: str | None = None,
    ) -> str:
        client = self.create_async_client()
        if client is None:
            return ""
        message = await client.messages.create(
            model=model or settings.ANTHROPIC_SMALL_MODEL or settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return extract_text_from_message(message)

    def generate_text_sync(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 768,
        model: str | None = None,
    ) -> str:
        client = self.create_sync_client()
        if client is None:
            return ""
        message = client.messages.create(
            model=model or settings.ANTHROPIC_SMALL_MODEL or settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return extract_text_from_message(message)
