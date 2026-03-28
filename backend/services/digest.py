from __future__ import annotations

import difflib
import json
from datetime import UTC
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Message, Run, Thread, Watcher, now


class DigestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def summarize_run(self, run: Run) -> str:
        if self.client is None:
            return self._fallback_run_summary(run)
        prompt = (
            "Summarize this coding run for a developer UI. "
            "Be concrete, one short paragraph, mention changed files or failure cause, "
            "and when the run failed include the most sensible next step.\n\n"
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
            "Return JSON array with classification, draftReply, and fixPlan. "
            "draftReply and fixPlan must be newly written operator-facing text. "
            "Do not repeat, quote, or paraphrase the original comment body as a full block. "
            "Only keep the reply or plan itself.\n\n"
            f"Memory:\n{memory_block}\n\nComments:\n{json.dumps(comments, ensure_ascii=False)}"
        )
        fallback = [self._fallback_comment_triage(comment) for comment in comments]
        text = await self._complete_text(prompt, json.dumps(fallback, ensure_ascii=False))
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return fallback
        normalized = []
        for base, item, fallback_item in zip(comments, payload, fallback, strict=False):
            body = str(base.get("body", "")).strip()
            classification = item.get("classification", "needs_input")
            normalized.append(
                {
                    "commentId": base.get("id"),
                    "reviewer": base.get("user", "reviewer"),
                    "path": base.get("path"),
                    "line": base.get("line"),
                    "body": body,
                    "classification": classification,
                    "draftReply": self._normalize_comment_generation(
                        original=body,
                        generated=item.get("draftReply", ""),
                        fallback=fallback_item["draftReply"],
                    ),
                    "fixPlan": self._normalize_comment_generation(
                        original=body,
                        generated=item.get("fixPlan", ""),
                        fallback=fallback_item["fixPlan"] if classification == "ai_can_fix" else "",
                    ),
                }
            )
        return normalized or fallback

    async def append_restore_summary(self, thread: Thread) -> bool:
        if not self._should_append_restore_summary(thread):
            return False

        latest_run = thread.runs[-1]
        summary = await self._restore_summary(thread, latest_run)
        message = Message(
            thread_id=thread.id,
            role="assistant",
            content=summary,
            metadata_={
                "kind": "restore-summary",
                "runId": latest_run.id,
                "summaryDate": now().date().isoformat(),
            },
        )
        self.db.add(message)
        await self.db.commit()
        return True

    def _should_append_restore_summary(self, thread: Thread) -> bool:
        if not thread.messages or not thread.runs:
            return False

        latest_message = thread.messages[-1]
        latest_message_date = self._date_in_utc(latest_message.created_at)
        return latest_message_date < now().date()

    async def _restore_summary(self, thread: Thread, latest_run: Run) -> str:
        fallback = self._fallback_restore_summary(thread, latest_run)
        if self.client is None:
            return fallback

        history = "\n".join(
            f"[{message.role}] {message.content[:240]}"
            for message in thread.messages[-5:]
            if (message.metadata_ or {}).get("kind") != "restore-summary"
        )
        prompt = (
            "Write a concise Chinese restore summary for a developer returning to an old task thread. "
            "Keep it to 1-3 sentences, concrete, and operator-friendly. Start with '上次做到这里：'.\n\n"
            f"Thread title: {thread.title}\n"
            f"Recent messages:\n{history or 'No recent messages.'}\n\n"
            f"Latest run status: {latest_run.status}\n"
            f"Latest run summary: {latest_run.result_summary or self._fallback_run_summary(latest_run)}\n"
            f"Changed files: {json.dumps(latest_run.changed_files or [], ensure_ascii=False)}"
        )
        return await self._complete_text(prompt, fallback)

    def _fallback_restore_summary(self, thread: Thread, latest_run: Run) -> str:
        summary = latest_run.result_summary or self._fallback_run_summary(latest_run)
        recent_user_message = next(
            (message.content for message in reversed(thread.messages) if message.role == "user"),
            None,
        )
        if recent_user_message:
            return f"上次做到这里：{summary} 最近在处理“{recent_user_message[:80]}”。"
        return f"上次做到这里：{summary}"

    def _date_in_utc(self, value) -> Any:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).date()

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
            return f"执行失败：{reason[:220]} 建议先查看最后一条报错并在修正后重试。"
        if run.status == "running":
            return "正在执行中。"
        return "任务已进入队列。"

    def _fallback_comment_triage(self, comment: dict[str, Any]) -> dict[str, Any]:
        body = (comment.get("body") or "").strip()
        lowered = body.lower()
        classification = (
            "needs_input"
            if any(token in lowered for token in {"why", "should", "clarify", "tradeoff", "?", "为什么", "是否", "解释", "取舍", "？"})
            else "ai_can_fix"
        )
        draft_reply = (
            "收到，我已经看过这条评论，会按建议调整实现。"
            if classification == "ai_can_fix"
            else "我采用当前实现是基于既定行为和取舍，下面把原因说明清楚。"
        )
        fix_plan = "按建议修改代码，并在更新后同步回复结果。" if classification == "ai_can_fix" else ""
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

    def _normalize_comment_generation(self, *, original: str, generated: Any, fallback: str) -> str:
        candidate = self._compact_comment_text(generated)
        original_text = self._compact_comment_text(original)
        fallback_text = self._compact_comment_text(fallback)

        if not candidate:
            return fallback_text
        if not original_text:
            return candidate

        stripped = self._strip_original_prefix(candidate, original_text)
        if stripped:
            return stripped

        similarity = difflib.SequenceMatcher(a=original_text, b=candidate).ratio()
        if candidate == original_text or similarity >= 0.82:
            return fallback_text
        return candidate

    def _strip_original_prefix(self, candidate: str, original: str) -> str:
        variants = [
            candidate,
            candidate.lstrip("“\"'"),
            candidate.replace("原文：", "", 1).strip(),
            candidate.replace("原评论：", "", 1).strip(),
            candidate.replace("评论：", "", 1).strip(),
        ]
        for variant in variants:
            if variant.startswith(original):
                rest = variant[len(original) :].lstrip("：:，,。；;？?）)]】>\n\r\t ")
                if rest:
                    return rest
        return ""

    def _compact_comment_text(self, value: Any) -> str:
        return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip("“”\"' ")
