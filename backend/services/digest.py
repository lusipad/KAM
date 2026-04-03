from __future__ import annotations

import json
from typing import Protocol

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings


class RunSummarySource(Protocol):
    task: str
    status: str
    changed_files: list[str] | None
    raw_output: str | None


class DigestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def summarize_run(self, run: RunSummarySource) -> str:
        fallback = self._fallback_run_summary(run)
        if self.client is None:
            return fallback

        prompt = (
            "Summarize this coding run for a developer UI. "
            "Be concrete, one short paragraph, mention changed files or failure cause, "
            "and when the run failed include the most sensible next step.\n\n"
            f"Task: {run.task}\nStatus: {run.status}\nChanged files: {json.dumps(run.changed_files or [])}\n"
            f"Raw output:\n{(run.raw_output or '')[:6000]}"
        )
        return await self._complete_text(prompt, fallback)

    async def _complete_text(self, prompt: str, fallback: str) -> str:
        try:
            response = await self.client.messages.create(
                model=settings.digest_model,
                max_tokens=320,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            return fallback

        fragments: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                fragments.append(text)
        return "".join(fragments).strip() or fallback

    def _fallback_run_summary(self, run: RunSummarySource) -> str:
        if run.status == "passed":
            files = ", ".join((run.changed_files or [])[:3])
            if files:
                return f"完成了任务，改动集中在 {files}。"
            return "任务完成，等待你决定是否采纳。"
        if run.status == "failed":
            tail = (run.raw_output or "").strip().splitlines()
            reason = tail[-1] if tail else "执行失败。"
            return f"执行失败：{reason[:220]} 建议先查看最后一条报错并在修正后重试。"
        if run.status == "running":
            return "正在执行中。"
        return "任务已进入队列。"
