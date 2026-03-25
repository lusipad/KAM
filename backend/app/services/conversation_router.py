"""
KAM v2 对话路由器：LLM 可用时优先，失败自动降级到规则路由。
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.context_assembler import ContextAssembler
from app.services.memory_service import MemoryService
from app.services.run_service import RunService


class ConversationRouter:
    EXECUTION_KEYWORDS = (
        "继续",
        "实现",
        "修复",
        "重构",
        "对比",
        "比较",
        "研究",
        "调研",
        "开始做",
        "补上",
        "分析",
        "写完",
        "做完",
    )

    def __init__(self, db: Session):
        self.db = db
        self.context_assembler = ContextAssembler(db)
        self.run_service = RunService(db)
        self.memory_service = MemoryService(db)

    def route(
        self,
        *,
        thread_id: str,
        message_id: str,
        user_message: str,
        create_run: bool | None = None,
        agent: str | None = None,
        command: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = self.context_assembler.assemble(thread_id) or {}
        llm_plan = self._route_with_llm(user_message, context)
        heuristic_preferences = self._extract_preferences(user_message, thread_id)
        llm_preferences = self._persist_llm_preferences(llm_plan.get("preferences") or [], thread_id)
        recorded_preferences = self._merge_preferences(heuristic_preferences, llm_preferences)

        should_run = self._resolve_should_run(user_message, create_run, llm_plan)
        agents = self._resolve_agents(llm_plan, agent, command)
        runs = []
        if should_run:
            prompt = self._build_run_prompt(user_message, context)
            for agent_spec in agents:
                run = self.run_service.create_run(
                    thread_id,
                    {
                        "agent": agent_spec.get("agent") or settings.DEFAULT_RUN_AGENT,
                        "command": agent_spec.get("command") or command,
                        "prompt": prompt,
                        "model": model or agent_spec.get("model"),
                        "reasoningEffort": reasoning_effort or agent_spec.get("reasoningEffort"),
                        "context": context,
                        "metadata": {
                            **(metadata or {}),
                            "routedBy": "conversation-router",
                            "routerModel": settings.ROUTER_MODEL,
                            "routerReasoningEffort": settings.ROUTER_REASONING_EFFORT,
                            "routerMode": llm_plan.get("mode") or "heuristic",
                        },
                    },
                    message_id=message_id,
                    auto_start=True,
                )
                if run:
                    runs.append(run)

        reply = self._build_reply(
            user_message=user_message,
            context=context,
            runs=runs,
            recorded_preferences=recorded_preferences,
            router_mode=llm_plan.get("mode") or "heuristic",
        )
        return {
            "reply": reply,
            "runs": [run.to_dict(include_artifacts=False) for run in runs],
            "preferences": recorded_preferences,
            "context": context,
            "routerMode": llm_plan.get("mode") or "heuristic",
        }

    def _route_with_llm(self, user_message: str, context: dict[str, Any]) -> dict[str, Any]:
        if not settings.OPENAI_API_KEY.strip():
            return {"mode": "heuristic"}

        payload = {
            "model": settings.ROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 KAM v2 的对话路由器。请严格只输出 JSON，不要输出 markdown。"
                        "JSON 结构："
                        '{"should_run": boolean, "agents": [{"agent": "codex|claude-code|custom", '
                        '"command": string|null, "model": string|null, "reasoningEffort": string|null}], '
                        '"preferences": [{"category": string, "key": string, "value": string}], '
                        '"summary": string}. '
                        "如果无需执行，should_run=false 且 agents=[]。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": user_message,
                            "contextSummary": context.get("summary") or "",
                            "pinnedResources": context.get("pinnedResources") or [],
                            "preferences": context.get("preferences") or [],
                            "decisions": context.get("decisions") or [],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(
                f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = self._parse_json_text(content)
            return {
                "mode": "llm",
                "should_run": bool(parsed.get("should_run", False)),
                "agents": parsed.get("agents") or [],
                "preferences": parsed.get("preferences") or [],
                "summary": parsed.get("summary") or "",
            }
        except Exception:
            return {"mode": "heuristic"}

    def _parse_json_text(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.startswith("```")]
            text = "\n".join(lines).strip()
        return json.loads(text or "{}")

    def _resolve_should_run(self, user_message: str, create_run: bool | None, llm_plan: dict[str, Any]) -> bool:
        if create_run is not None:
            return create_run
        if "should_run" in llm_plan:
            return bool(llm_plan["should_run"])
        return self._looks_like_execution(user_message)

    def _resolve_agents(self, llm_plan: dict[str, Any], agent: str | None, command: str | None) -> list[dict[str, Any]]:
        llm_agents = llm_plan.get("agents") or []
        if llm_agents:
            return llm_agents
        return [
            {
                "agent": agent or settings.DEFAULT_RUN_AGENT,
                "command": command,
                "model": settings.CODEX_MODEL if (agent or settings.DEFAULT_RUN_AGENT) == "codex" else None,
                "reasoningEffort": settings.CODEX_REASONING_EFFORT if (agent or settings.DEFAULT_RUN_AGENT) == "codex" else None,
            }
        ]

    def _looks_like_execution(self, user_message: str) -> bool:
        text = user_message.strip().lower()
        return any(keyword in text for keyword in self.EXECUTION_KEYWORDS)

    def _extract_preferences(self, user_message: str, thread_id: str) -> list[dict[str, Any]]:
        normalized = user_message.lower()
        recorded = []

        if "pnpm" in normalized and any(token in normalized for token in ["默认", "prefer", "用", "使用"]):
            preference = self.memory_service.create_preference(
                {
                    "category": "tool",
                    "key": "package-manager",
                    "value": "pnpm",
                    "sourceThreadId": thread_id,
                }
            )
            recorded.append(preference.to_dict())

        if any(token in normalized for token in ["函数式", "functional"]) and any(
            token in normalized for token in ["组件", "风格", "prefer", "默认"]
        ):
            preference = self.memory_service.create_preference(
                {
                    "category": "code_style",
                    "key": "component-style",
                    "value": "functional",
                    "sourceThreadId": thread_id,
                }
            )
            recorded.append(preference.to_dict())

        if ("不要 class" in normalized) or ("avoid class" in normalized):
            preference = self.memory_service.create_preference(
                {
                    "category": "code_style",
                    "key": "avoid-class-components",
                    "value": "true",
                    "sourceThreadId": thread_id,
                }
            )
            recorded.append(preference.to_dict())

        return recorded

    def _persist_llm_preferences(self, preferences: list[dict[str, Any]], thread_id: str) -> list[dict[str, Any]]:
        recorded = []
        for item in preferences:
            category = str(item.get("category") or "general").strip()
            key = str(item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            if not key or not value:
                continue
            preference = self.memory_service.create_preference(
                {
                    "category": category,
                    "key": key,
                    "value": value,
                    "sourceThreadId": thread_id,
                }
            )
            recorded.append(preference.to_dict())
        return recorded

    def _merge_preferences(self, left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in [*left, *right]:
            key = (str(item.get("category") or ""), str(item.get("key") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _build_run_prompt(self, user_message: str, context: dict[str, Any]) -> str:
        summary = context.get("summary") or "暂无上下文摘要。"
        pinned_resources = context.get("pinnedResources") or []
        preferences = context.get("preferences") or []
        decisions = context.get("decisions") or []

        lines = [
            "# Task",
            user_message.strip(),
            "",
            "# Context Summary",
            summary,
        ]

        if pinned_resources:
            lines.extend([
                "",
                "# Pinned Resources",
                *[
                    f"- [{resource.get('type')}] {resource.get('title') or resource.get('uri')}: {resource.get('uri')}"
                    for resource in pinned_resources[:8]
                ],
            ])

        if preferences:
            lines.extend([
                "",
                "# Preferences",
                *[
                    f"- {item.get('category')} / {item.get('key')}: {item.get('value')}"
                    for item in preferences[:8]
                ],
            ])

        if decisions:
            lines.extend([
                "",
                "# Decisions",
                *[
                    f"- {item.get('question')}: {item.get('decision')}"
                    for item in decisions[:5]
                ],
            ])

        return "\n".join(lines)

    def _build_reply(
        self,
        *,
        user_message: str,
        context: dict[str, Any],
        runs: list[Any],
        recorded_preferences: list[dict[str, Any]],
        router_mode: str,
    ) -> str:
        reply_lines = []
        if recorded_preferences:
            memory_text = "，".join(f"{item['key']}={item['value']}" for item in recorded_preferences)
            reply_lines.append(f"我记住了这些偏好：{memory_text}。")

        if runs:
            if len(runs) == 1:
                run = runs[0]
                reply_lines.append(
                    f"已基于当前 Thread 自动创建 1 个 {run.agent} run，默认模型 {run.model or '未指定'} / {run.reasoning_effort or 'default'}。"
                )
            else:
                agents = "、".join(run.agent for run in runs)
                reply_lines.append(f"已并发创建 {len(runs)} 个 runs：{agents}。")
            if context.get("summary"):
                reply_lines.append("我会把最近对话摘要、钉住资源、历史偏好和决策一并注入到这次执行。")
            if router_mode == "llm":
                reply_lines.append("本轮意图判断已优先使用 LLM 路由。")
        else:
            reply_lines.append("我已把这条消息记入当前 Thread。")
            if self._looks_like_execution(user_message):
                reply_lines.append("如果你希望我直接开跑，也可以在发送时显式打开自动 Run。")

        return " ".join(reply_lines)
