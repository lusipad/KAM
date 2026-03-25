"""
KAM v2 对话路由器：LLM 可用时优先，失败自动降级到规则路由。
"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

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
        project_id = str((context.get("project") or {}).get("id") or "").strip() or None
        llm_decisions = self._persist_llm_decisions(llm_plan.get("decisions") or [], project_id, thread_id)
        llm_learnings = self._persist_llm_learnings(llm_plan.get("learnings") or [], project_id, thread_id)
        recorded_preferences = self._merge_preferences(heuristic_preferences, llm_preferences)

        should_run = self._resolve_should_run(user_message, create_run, llm_plan)
        agents = self._resolve_agents(llm_plan, agent, command, user_message)
        compare_group_id = str(uuid4()) if should_run and len(agents) > 1 else None
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
                            **({
                                "compareGroupId": compare_group_id,
                                "compareLabel": agent_spec.get("label") or agent_spec.get("agent") or settings.DEFAULT_RUN_AGENT,
                                "comparePrompt": user_message.strip(),
                            } if compare_group_id else {}),
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
            recorded_decisions=llm_decisions,
            recorded_learnings=llm_learnings,
            planner_summary=llm_plan.get("summary") or "",
            router_mode=llm_plan.get("mode") or "heuristic",
        )
        return {
            "reply": reply,
            "runs": [run.to_dict(include_artifacts=False) for run in runs],
            "preferences": recorded_preferences,
            "decisions": llm_decisions,
            "learnings": llm_learnings,
            "context": context,
            "routerMode": llm_plan.get("mode") or "heuristic",
            "compareId": compare_group_id,
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
                        "你是 KAM v2 的对话路由器。"
                        "你必须调用函数 plan_kam_response 来输出结构化计划，不要输出 markdown。"
                        "只有在用户明确表达长期偏好时才写 preferences。"
                        "只有在用户明确做出方案选择、结论确认时才写 decisions。"
                        "只有在用户陈述稳定、可复用的项目经验时才写 learnings。"
                        "如果用户想比较多个 agent，请把 mode 设为 compare 并返回多个 agents。"
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
                            "learnings": context.get("learnings") or [],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "tools": [self._planner_tool()],
            "tool_choice": {
                "type": "function",
                "function": {
                    "name": "plan_kam_response",
                },
            },
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
            message = response.json()["choices"][0]["message"]
            parsed = self._extract_llm_plan(message)
            return {
                "mode": "llm",
                "should_run": bool(parsed.get("should_run", False)),
                "agents": parsed.get("agents") or [],
                "preferences": parsed.get("preferences") or [],
                "decisions": parsed.get("decisions") or [],
                "learnings": parsed.get("learnings") or [],
                "summary": parsed.get("summary") or "",
            }
        except Exception:
            return {"mode": "heuristic"}

    def _planner_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "plan_kam_response",
                "description": "Plan whether KAM should reply only, create one run, or create a compare run group.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "should_run": {
                            "type": "boolean",
                            "description": "Whether KAM should create runs for this message.",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["chat", "single_run", "compare"],
                            "description": "Routing mode for this message.",
                        },
                        "agents": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "agent": {
                                        "type": "string",
                                        "enum": ["codex", "claude-code", "custom"],
                                    },
                                    "label": {"type": ["string", "null"]},
                                    "command": {"type": ["string", "null"]},
                                    "model": {"type": ["string", "null"]},
                                    "reasoningEffort": {"type": ["string", "null"]},
                                },
                                "required": ["agent"],
                                "additionalProperties": False,
                            },
                        },
                        "preferences": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "category": {"type": "string"},
                                    "key": {"type": "string"},
                                    "value": {"type": "string"},
                                },
                                "required": ["key", "value"],
                                "additionalProperties": False,
                            },
                        },
                        "decisions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "decision": {"type": "string"},
                                    "reasoning": {"type": ["string", "null"]},
                                },
                                "required": ["decision"],
                                "additionalProperties": False,
                            },
                        },
                        "learnings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                },
                                "required": ["content"],
                                "additionalProperties": False,
                            },
                        },
                        "summary": {
                            "type": "string",
                            "description": "A concise assistant-facing summary of what KAM understood or will do.",
                        },
                    },
                    "required": ["should_run", "mode", "agents", "preferences", "decisions", "learnings", "summary"],
                    "additionalProperties": False,
                },
            },
        }

    def _extract_llm_plan(self, message: dict[str, Any]) -> dict[str, Any]:
        tool_calls = message.get("tool_calls") or []
        for tool_call in tool_calls:
            function_payload = tool_call.get("function") or {}
            if function_payload.get("name") != "plan_kam_response":
                continue
            arguments = function_payload.get("arguments") or "{}"
            parsed = self._parse_json_text(arguments)
            return {
                "should_run": bool(parsed.get("should_run", False)),
                "mode": str(parsed.get("mode") or "chat"),
                "agents": parsed.get("agents") or [],
                "preferences": parsed.get("preferences") or [],
                "decisions": parsed.get("decisions") or [],
                "learnings": parsed.get("learnings") or [],
                "summary": str(parsed.get("summary") or "").strip(),
            }

        content = message.get("content") or ""
        parsed = self._parse_json_text(content) if content else {}
        return {
            "should_run": bool(parsed.get("should_run", False)),
            "mode": str(parsed.get("mode") or "chat"),
            "agents": parsed.get("agents") or [],
            "preferences": parsed.get("preferences") or [],
            "decisions": parsed.get("decisions") or [],
            "learnings": parsed.get("learnings") or [],
            "summary": str(parsed.get("summary") or "").strip(),
        }

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

    def _resolve_agents(self, llm_plan: dict[str, Any], agent: str | None, command: str | None, user_message: str) -> list[dict[str, Any]]:
        llm_agents = llm_plan.get("agents") or []
        if llm_agents:
            return llm_agents
        if not agent and self._looks_like_compare(user_message):
            return [
                {
                    "agent": "codex",
                    "label": "Codex",
                    "command": None,
                    "model": settings.CODEX_MODEL,
                    "reasoningEffort": settings.CODEX_REASONING_EFFORT,
                },
                {
                    "agent": "claude-code",
                    "label": "Claude Code",
                    "command": None,
                    "model": None,
                    "reasoningEffort": None,
                },
            ]

        resolved_agent = agent or settings.DEFAULT_RUN_AGENT
        resolved_label = {
            "codex": "Codex",
            "claude-code": "Claude Code",
            "custom": "Custom Command",
        }.get(resolved_agent, resolved_agent)
        return [
            {
                "agent": resolved_agent,
                "label": resolved_label,
                "command": command,
                "model": settings.CODEX_MODEL if resolved_agent == "codex" else None,
                "reasoningEffort": settings.CODEX_REASONING_EFFORT if resolved_agent == "codex" else None,
            }
        ]

    def _looks_like_compare(self, user_message: str) -> bool:
        text = user_message.strip().lower()
        return any(keyword in text for keyword in ["对比", "比较", "compare", "vs", "versus"])

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

    def _persist_llm_decisions(
        self,
        decisions: list[dict[str, Any]],
        project_id: str | None,
        thread_id: str,
    ) -> list[dict[str, Any]]:
        if not project_id:
            return []

        recorded = []
        for item in decisions:
            decision_value = str(item.get("decision") or "").strip()
            question = str(item.get("question") or "").strip() or "本轮确认的方案"
            if not decision_value:
                continue
            decision = self.memory_service.ensure_decision(
                {
                    "projectId": project_id,
                    "question": question,
                    "decision": decision_value,
                    "reasoning": str(item.get("reasoning") or "").strip(),
                    "sourceThreadId": thread_id,
                }
            )
            recorded.append(decision.to_dict())
        return recorded

    def _persist_llm_learnings(
        self,
        learnings: list[dict[str, Any]],
        project_id: str | None,
        thread_id: str,
    ) -> list[dict[str, Any]]:
        if not project_id:
            return []

        recorded = []
        for item in learnings:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            learning = self.memory_service.ensure_learning(
                {
                    "projectId": project_id,
                    "content": content,
                    "sourceThreadId": thread_id,
                }
            )
            if learning:
                recorded.append(learning.to_dict())
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
        learnings = context.get("learnings") or []

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

        if learnings:
            lines.extend([
                "",
                "# Project Learnings",
                *[
                    f"- {item.get('content')}"
                    for item in learnings[:5]
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
        recorded_decisions: list[dict[str, Any]],
        recorded_learnings: list[dict[str, Any]],
        planner_summary: str,
        router_mode: str,
    ) -> str:
        reply_lines = []
        if planner_summary:
            reply_lines.append(planner_summary)

        if recorded_preferences:
            memory_text = "，".join(f"{item['key']}={item['value']}" for item in recorded_preferences)
            reply_lines.append(f"我记住了这些偏好：{memory_text}。")

        if recorded_decisions:
            decision_text = "；".join(
                f"{item.get('question') or '本轮决策'} → {item['decision']}"
                for item in recorded_decisions[:2]
            )
            reply_lines.append(f"我已记录这次决策：{decision_text}。")

        if recorded_learnings:
            learning_text = "；".join(str(item.get("content") or "")[:72] for item in recorded_learnings[:2])
            reply_lines.append(f"我也把这些项目经验沉淀进记忆：{learning_text}。")

        context_preferences = self._format_context_preferences(context.get("preferences") or [], recorded_preferences)
        if context_preferences:
            reply_lines.append(f"我会沿用你的历史偏好：{context_preferences}。")

        context_decisions = self._format_context_decisions(context.get("decisions") or [])
        if context_decisions:
            reply_lines.append(f"我也会延续这些历史决策：{context_decisions}。")

        context_learnings = self._format_context_learnings(context.get("learnings") or [])
        if context_learnings:
            reply_lines.append(f"我会参考这些项目经验：{context_learnings}。")

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
                reply_lines.append("我已自动组装当前 Project、最近 Thread 摘要、钉住资源、历史偏好和决策作为执行上下文。")
            if router_mode == "llm":
                reply_lines.append("本轮意图判断已优先使用 LLM 路由。")
        else:
            reply_lines.append("我已把这条消息记入当前 Thread。")
            if self._looks_like_execution(user_message):
                reply_lines.append("如果你希望我直接开跑，也可以在发送时显式打开自动 Run。")

        return " ".join(reply_lines)

    def _format_context_preferences(
        self,
        preferences: list[dict[str, Any]],
        recorded_preferences: list[dict[str, Any]],
    ) -> str:
        recorded_keys = {
            (str(item.get("category") or ""), str(item.get("key") or ""))
            for item in recorded_preferences
        }
        items: list[str] = []
        for item in preferences:
            key = (str(item.get("category") or ""), str(item.get("key") or ""))
            if key in recorded_keys:
                continue
            label = str(item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            if not label or not value:
                continue
            items.append(f"{label}={value}")
            if len(items) >= 3:
                break
        return "；".join(items)

    def _format_context_decisions(self, decisions: list[dict[str, Any]]) -> str:
        items: list[str] = []
        for item in decisions:
            question = str(item.get("question") or "").strip()
            decision = str(item.get("decision") or "").strip()
            if not decision:
                continue
            items.append(f"{question} → {decision}" if question else decision)
            if len(items) >= 2:
                break
        return "；".join(items)

    def _format_context_learnings(self, learnings: list[dict[str, Any]]) -> str:
        items: list[str] = []
        for item in learnings:
            content = " ".join(str(item.get("content") or "").strip().split())
            if not content:
                continue
            items.append(content[:72])
            if len(items) >= 2:
                break
        return "；".join(items)
