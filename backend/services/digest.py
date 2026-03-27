from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Message, Run, Thread, Watcher


class DigestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def summarize_run(self, run: Run) -> str:
        if self.client is None:
            return self._fallback_run_summary(run)
        prompt = (
            "Summarize this coding run for a developer UI. "
            "Be concrete, one short paragraph, and mention changed files or failure cause.\n\n"
            f"Task: {run.task}\nStatus: {run.status}\nChanged files: {json.dumps(run.changed_files or [])}\n"
            f"Raw output:\n{(run.raw_output or '')[:6000]}"
        )
        return await self._complete_text(prompt, self._fallback_run_summary(run))

    async def summarize_watcher_event(self, watcher: Watcher, changes: dict[str, Any]) -> str:
        if self.client is None:
            created = len(changes.get("created", []))
            updated = len(changes.get("updated", []))
            return f"{watcher.name} 检测到 {created} 个新增项、{updated} 个更新项。"
        prompt = (
            "Summarize this watcher event in concise, operator-friendly language.\n\n"
            f"Watcher: {watcher.name} ({watcher.source_type})\nChanges:\n{json.dumps(changes, ensure_ascii=False)[:6000]}"
        )
        return await self._complete_text(prompt, f"{watcher.name} 产生了新的后台事件。")

    async def triage_pr_comments(self, comments: list[dict[str, Any]], memory_block: str) -> list[dict[str, Any]]:
        if not comments:
            return []
        if self.client is None:
            return [self._fallback_comment_triage(comment) for comment in comments]
        prompt = (
            "Classify each PR review comment as needs_input or ai_can_fix. "
            "Return JSON array with classification, draftReply, and fixPlan.\n\n"
            f"Memory:\n{memory_block}\n\nComments:\n{json.dumps(comments, ensure_ascii=False)}"
        )
        fallback = [self._fallback_comment_triage(comment) for comment in comments]
        text = await self._complete_text(prompt, json.dumps(fallback, ensure_ascii=False))
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return fallback
        normalized = []
        for base, item in zip(comments, payload, strict=False):
            normalized.append(
                {
                    "commentId": base.get("id"),
                    "reviewer": base.get("user", "reviewer"),
                    "path": base.get("path"),
                    "line": base.get("line"),
                    "body": base.get("body", ""),
                    "classification": item.get("classification", "needs_input"),
                    "draftReply": item.get("draftReply", ""),
                    "fixPlan": item.get("fixPlan", ""),
                }
            )
        return normalized or fallback

    async def append_restore_summary(self, thread: Thread) -> None:
        if not thread.runs:
            return
        latest = thread.runs[-1]
        summary = latest.result_summary or self._fallback_run_summary(latest)
        message = Message(
            thread_id=thread.id,
            role="assistant",
            content=f"上次做到这里：{summary}",
            metadata_={"kind": "restore-summary", "runId": latest.id},
        )
        self.db.add(message)
        await self.db.commit()

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
        fragments = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                fragments.append(text)
        return "".join(fragments).strip() or fallback

    def _fallback_run_summary(self, run: Run) -> str:
        if run.status == "passed":
            files = ", ".join((run.changed_files or [])[:3])
            if files:
                return f"完成了任务，改动集中在 {files}。"
            return "任务完成，等待你决定是否采纳。"
        if run.status == "failed":
            tail = (run.raw_output or "").strip().splitlines()
            reason = tail[-1] if tail else "执行失败。"
            return f"执行失败：{reason[:220]}"
        if run.status == "running":
            return "正在执行中。"
        return "任务已进入队列。"

    def _fallback_comment_triage(self, comment: dict[str, Any]) -> dict[str, Any]:
        body = (comment.get("body") or "").strip()
        lowered = body.lower()
        classification = "needs_input" if any(token in lowered for token in {"why", "should", "clarify", "tradeoff", "?"}) else "ai_can_fix"
        draft_reply = "Thanks. I reviewed this and will adjust the implementation." if classification == "ai_can_fix" else "I considered this tradeoff for the current approach because it preserves the intended behavior."
        fix_plan = "Apply the suggested code change and reply once updated." if classification == "ai_can_fix" else ""
        return {
            "commentId": comment.get("id"),
            "reviewer": comment.get("user", "reviewer"),
            "path": comment.get("path"),
            "line": comment.get("line"),
            "body": body,
            "classification": classification,
            "draftReply": draft_reply,
            "fixPlan": fix_plan,
        }
