from __future__ import annotations

import json
import re

from anthropic import AsyncAnthropic

from config import settings


class TitleGenerationService:
    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def generate(self, prompt: str, *, repo_path: str | None = None) -> tuple[str, str]:
        fallback = self._fallback_titles(prompt, repo_path=repo_path)
        if self.client is None:
            return fallback

        system = (
            "你负责为 KAM 生成项目标题和线程标题。\n"
            "要求：\n"
            "1. 输出严格 JSON，键为 projectTitle 和 threadTitle。\n"
            "2. 标题必须是简短中文，像真实工作项，不要复述整段需求。\n"
            "3. projectTitle 更偏工作域或仓库上下文；threadTitle 更偏当前要处理的具体任务。\n"
            "4. projectTitle 不超过 18 个汉字或 36 个英文字符；threadTitle 不超过 24 个汉字或 48 个英文字符。"
        )
        user_prompt = f"用户首条输入：{prompt.strip()}\n仓库路径：{repo_path or '无'}"
        try:
            response = await self.client.messages.create(
                model=settings.chat_model,
                max_tokens=180,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception:
            return fallback

        text = "".join(getattr(block, "text", "") for block in response.content).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return fallback

        project_title = self._clean_title(str(payload.get("projectTitle", "")).strip(), fallback[0], limit=36)
        thread_title = self._clean_title(str(payload.get("threadTitle", "")).strip(), fallback[1], limit=48)
        return project_title, thread_title

    def _fallback_titles(self, prompt: str, *, repo_path: str | None) -> tuple[str, str]:
        compact = " ".join(prompt.strip().split())
        repo_segment = None
        if repo_path:
            parts = [part for part in re.split(r"[\\/]", repo_path) if part]
            repo_segment = parts[-1] if parts else None

        project_title = repo_segment or self._project_title_from_prompt(compact)
        thread_title = self._thread_title_from_prompt(compact)
        return self._clean_title(project_title, "新项目", limit=36), self._clean_title(thread_title, "新对话", limit=48)

    def _project_title_from_prompt(self, prompt: str) -> str:
        for separator in ("，", ",", "。", ".", ":", "：", "\n"):
            if separator in prompt:
                head = prompt.split(separator, 1)[0].strip()
                if head:
                    return head[:36]
        return prompt[:36] or "新项目"

    def _thread_title_from_prompt(self, prompt: str) -> str:
        patterns = [
            r"(修复[^，。,.]{0,24})",
            r"(实现[^，。,.]{0,24})",
            r"(重构[^，。,.]{0,24})",
            r"(部署[^，。,.]{0,24})",
            r"(监控[^，。,.]{0,24})",
            r"(检查[^，。,.]{0,24})",
        ]
        for pattern in patterns:
            matched = re.search(pattern, prompt)
            if matched:
                return matched.group(1)
        return prompt[:48] or "新对话"

    def _clean_title(self, title: str, default: str, *, limit: int) -> str:
        compact = " ".join(title.split()).strip(" -_.,:：")
        if not compact:
            compact = default
        return compact[:limit]
