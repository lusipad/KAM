"""
KAM v2 对话路由器：Anthropic 优先，失败时回退到规则路由。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation import Message, Thread
from app.services.anthropic_service import AnthropicService, extract_text_from_message, iter_tool_uses
from app.services.context_assembler import ContextAssembler
from app.services.memory_service import MemoryService
from app.services.run_service import RunService
from app.services.skill_service import SkillService
from app.services.thread_service import ThreadService


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
        self.skill_service = SkillService(db)
        self.thread_service = ThreadService(db)
        self.anthropic = AnthropicService()

    async def route(
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
        result = {
            "reply": "",
            "runs": [],
            "preferences": [],
            "decisions": [],
            "learnings": [],
            "context": {},
            "routerMode": "heuristic",
            "compareId": None,
        }
        streamed_reply = ""
        async for event in self.route_async(
            thread_id=thread_id,
            message_id=message_id,
            user_message=user_message,
            create_run=create_run,
            agent=agent,
            command=command,
            model=model,
            reasoning_effort=reasoning_effort,
            metadata=metadata,
        ):
            event_type = event.get("type")
            if event_type == "text_delta":
                streamed_reply += str(event.get("delta") or "")
                continue
            if event_type == "assistant_reply_final":
                result["reply"] = str(event.get("content") or "").strip()
                continue
            if event_type == "runs_created":
                result["runs"] = event.get("runs") or []
                result["compareId"] = event.get("compareId")
                continue
            if event_type == "memory_recorded":
                kind = str(event.get("kind") or "")
                if kind == "preference":
                    result["preferences"].append(event["record"])
                elif kind == "decision":
                    result["decisions"].append(event["record"])
                elif kind == "learning":
                    result["learnings"].append(event["record"])
                continue
            if event_type == "done":
                result["context"] = event.get("context") or {}
                result["routerMode"] = str(event.get("routerMode") or "heuristic")
                result["compareId"] = event.get("compareId")

        if not result["reply"]:
            result["reply"] = streamed_reply.strip()
        return result

    async def route_async(
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
    ) -> AsyncGenerator[dict[str, Any], None]:
        context = self.context_assembler.assemble(thread_id) or {}
        project = context.get("project") or {}
        project_id = str(project.get("id") or "").strip() or None
        repo_path = str(project.get("repoPath") or "").strip() or None
        if project_id and repo_path:
            self.skill_service.sync_project_skills(project_id, repo_path)

        skill_invocation = self._try_expand_skill(user_message, project_id)
        effective_message = skill_invocation.get("expanded_prompt") if skill_invocation else user_message
        effective_agent = agent or (skill_invocation.get("agent") if skill_invocation else None)
        effective_metadata = {
            **(metadata or {}),
            **(
                {
                    "skillName": skill_invocation["skill"].name,
                    "skillSource": skill_invocation["skill"].source,
                    "skillInstructions": skill_invocation["skill"].prompt_template,
                }
                if skill_invocation
                else {}
            ),
        }
        heuristic_preferences = self._extract_preferences(user_message, thread_id)
        if self.anthropic.enabled:
            try:
                async for event in self._route_with_anthropic(
                    thread_id=thread_id,
                    message_id=message_id,
                    user_message=effective_message,
                    context=context,
                    create_run=True if skill_invocation and create_run is None else create_run,
                    agent=effective_agent,
                    command=command,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    metadata=effective_metadata,
                    heuristic_preferences=heuristic_preferences,
                ):
                    yield event
                return
            except Exception:
                pass

        async for event in self._route_with_heuristic(
            thread_id=thread_id,
            message_id=message_id,
            user_message=effective_message,
            context=context,
            create_run=True if skill_invocation and create_run is None else create_run,
            agent=effective_agent,
            command=command,
            model=model,
            reasoning_effort=reasoning_effort,
            metadata=effective_metadata,
            heuristic_preferences=heuristic_preferences,
        ):
            yield event

    async def ensure_restore_summary(self, thread_id: str) -> str | None:
        thread = self.db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread or not thread.messages:
            return None

        last_message = list(thread.messages)[-1]
        if last_message.created_at and last_message.created_at.date() == datetime.utcnow().date():
            return None

        latest_restore = (
            self.db.query(Message)
            .filter(Message.thread_id == thread_id, Message.role == "assistant")
            .order_by(Message.created_at.desc())
            .first()
        )
        if latest_restore and (latest_restore.metadata_ or {}).get("generatedBy") == "restore-summary":
            if latest_restore.created_at and latest_restore.created_at.date() == datetime.utcnow().date():
                return latest_restore.content

        summary = await self.generate_restore_summary(thread_id)
        if not summary:
            return None

        message = self.thread_service.create_message(
            thread_id,
            {
                "role": "assistant",
                "content": summary,
                "metadata": {"generatedBy": "restore-summary"},
            },
        )
        return message.content if message else summary

    async def generate_restore_summary(self, thread_id: str) -> str:
        context = self.context_assembler.assemble(thread_id) or {}
        if not context:
            return ""
        if self.anthropic.enabled:
            prompt = await self.anthropic.generate_text(
                system=(
                    "你是 KAM 的状态恢复助手。"
                    "根据上下文给出 1 到 3 句话的恢复摘要，说明上次做到哪、最近一次 run 结果、下一步建议。"
                    "只输出摘要正文。"
                ),
                messages=[
                    {
                        "role": "user",
                        "content": self._build_context_packet(context),
                    }
                ],
                max_tokens=220,
                model=settings.ANTHROPIC_SMALL_MODEL,
            )
            if prompt.strip():
                return prompt.strip()

        summary = context.get("summary") or ""
        recent_runs = context.get("recentRuns") or []
        run_summary = ""
        if recent_runs:
            latest = recent_runs[0]
            latest_summary = str(latest.get("summary") or "").strip()
            if latest_summary:
                run_summary = f"最近一次 {latest.get('agent') or 'agent'} run 状态为 {latest.get('status') or 'unknown'}，{latest_summary[:120]}"
        parts = [part for part in [summary.strip(), run_summary.strip()] if part]
        return " ".join(parts)[:280]

    async def _route_with_anthropic(
        self,
        *,
        thread_id: str,
        message_id: str,
        user_message: str,
        context: dict[str, Any],
        create_run: bool | None,
        agent: str | None,
        command: str | None,
        model: str | None,
        reasoning_effort: str | None,
        metadata: dict[str, Any] | None,
        heuristic_preferences: list[dict[str, Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        client = self.anthropic.create_async_client()
        if client is None:
            raise RuntimeError("Anthropic client unavailable")

        reply_chunks: list[str] = []
        async with client.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2048,
            system=self._build_system_prompt(context),
            messages=[
                {
                    "role": "user",
                    "content": self._build_context_packet(context, user_message=user_message),
                }
            ],
            tools=[
                self._create_run_tool(),
                self._record_memory_tool(),
            ],
        ) as stream:
            async for delta in stream.text_stream:
                text = str(delta or "")
                if not text:
                    continue
                reply_chunks.append(text)
                yield {"type": "text_delta", "delta": text}
            final_message = await stream.get_final_message()

        llm_preferences: list[dict[str, Any]] = []
        llm_decisions: list[dict[str, Any]] = []
        llm_learnings: list[dict[str, Any]] = []
        created_runs: list[dict[str, Any]] = []
        compare_group_id: str | None = None

        for record in heuristic_preferences:
            yield {"type": "memory_recorded", "kind": "preference", "record": record}

        for tool_call in iter_tool_uses(final_message):
            tool_name = str(tool_call.get("name") or "").strip()
            tool_input = tool_call.get("input") or {}
            if tool_name == "create_run":
                if create_run is False:
                    continue
                created = self._create_run_from_tool(
                    thread_id=thread_id,
                    message_id=message_id,
                    context=context,
                    tool_input=tool_input,
                    fallback_user_message=user_message,
                    agent_override=agent,
                    command=command,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    metadata=metadata,
                )
                if created:
                    created_runs.extend(created)
                continue
            if tool_name == "record_memory":
                recorded = self._record_memory_from_tool(
                    tool_input,
                    thread_id=thread_id,
                    project_id=str((context.get("project") or {}).get("id") or "").strip() or None,
                )
                if not recorded:
                    continue
                kind, record = recorded
                if kind == "preference":
                    llm_preferences.append(record)
                elif kind == "decision":
                    llm_decisions.append(record)
                elif kind == "learning":
                    llm_learnings.append(record)
                yield {"type": "memory_recorded", "kind": kind, "record": record}

        if create_run and not created_runs:
            fallback_runs, compare_group_id = self._create_runs_heuristically(
                thread_id=thread_id,
                message_id=message_id,
                user_message=user_message,
                context=context,
                agent=agent,
                command=command,
                model=model,
                reasoning_effort=reasoning_effort,
                metadata=metadata,
                create_run=True,
            )
            created_runs.extend(fallback_runs)
        elif len(created_runs) > 1:
            compare_group_id = str(uuid4())

        if created_runs:
            yield {
                "type": "runs_created",
                "runs": created_runs,
                "compareId": compare_group_id,
            }

        reply_text = extract_text_from_message(final_message) or "".join(reply_chunks).strip()
        if not reply_text:
            reply_text = self._build_fallback_reply(
                user_message=user_message,
                context=context,
                runs=created_runs,
                recorded_preferences=self._merge_preferences(heuristic_preferences, llm_preferences),
                recorded_decisions=llm_decisions,
                recorded_learnings=llm_learnings,
                router_mode="llm",
            )

        yield {"type": "assistant_reply_final", "content": reply_text}
        yield {
            "type": "done",
            "context": context,
            "routerMode": "llm",
            "compareId": compare_group_id,
        }

    async def _route_with_heuristic(
        self,
        *,
        thread_id: str,
        message_id: str,
        user_message: str,
        context: dict[str, Any],
        create_run: bool | None,
        agent: str | None,
        command: str | None,
        model: str | None,
        reasoning_effort: str | None,
        metadata: dict[str, Any] | None,
        heuristic_preferences: list[dict[str, Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        created_runs, compare_group_id = self._create_runs_heuristically(
            thread_id=thread_id,
            message_id=message_id,
            user_message=user_message,
            context=context,
            agent=agent,
            command=command,
            model=model,
            reasoning_effort=reasoning_effort,
            metadata=metadata,
            create_run=create_run,
        )
        reply = self._build_fallback_reply(
            user_message=user_message,
            context=context,
            runs=created_runs,
            recorded_preferences=heuristic_preferences,
            recorded_decisions=[],
            recorded_learnings=[],
            router_mode="heuristic",
        )

        for record in heuristic_preferences:
            yield {"type": "memory_recorded", "kind": "preference", "record": record}

        if created_runs:
            yield {
                "type": "runs_created",
                "runs": created_runs,
                "compareId": compare_group_id,
            }

        for chunk in self._chunk_text(reply):
            yield {"type": "text_delta", "delta": chunk}
            await asyncio.sleep(0)

        yield {"type": "assistant_reply_final", "content": reply}
        yield {
            "type": "done",
            "context": context,
            "routerMode": "heuristic",
            "compareId": compare_group_id,
        }

    def _build_system_prompt(self, context: dict[str, Any]) -> str:
        return (
            "你是 KAM 的 AI 控制台。"
            "先用自然中文回复用户，必要时再调用工具。"
            "当用户明确要求实现、修复、继续执行、对比多个 agent 时，调用 create_run。"
            "当用户明确表达长期偏好、方案决策或稳定经验时，调用 record_memory。"
            "回复保持直接、具体，不要复述整段上下文。"
            f"\n\n当前上下文摘要：\n{context.get('summary') or '暂无摘要。'}"
        )

    def _build_context_packet(self, context: dict[str, Any], user_message: str | None = None) -> str:
        project = context.get("project") or {}
        payload = {
            "project": {
                "id": project.get("id"),
                "title": project.get("title"),
                "description": project.get("description"),
                "repoPath": project.get("repoPath"),
                "checkCommands": project.get("checkCommands") or [],
            },
            "thread": context.get("thread") or {},
            "summary": context.get("summary") or "",
            "historyText": context.get("historyText") or "",
            "recentRuns": context.get("recentRuns") or [],
            "pinnedResources": context.get("pinnedResources") or [],
            "preferences": context.get("preferences") or [],
            "decisions": context.get("decisions") or [],
            "learnings": context.get("learnings") or [],
            "userMessage": user_message or "",
        }
        return json.dumps(payload, ensure_ascii=False)

    def _create_run_tool(self) -> dict[str, Any]:
        return {
            "name": "create_run",
            "description": "当需要真正执行代码修改、修复、调研或多 agent 对比时创建一个 run。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "给 Agent 的完整任务描述，需要包含目标、边界与验收标准。",
                    },
                    "agent": {
                        "type": "string",
                        "enum": ["codex", "claude-code", "custom"],
                        "description": "首选 agent。",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "为什么创建这个 run。",
                    },
                },
                "required": ["task_description"],
            },
        }

    def _record_memory_tool(self) -> dict[str, Any]:
        return {
            "name": "record_memory",
            "description": "记录用户偏好、项目决策或稳定经验。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["preference", "decision", "learning"],
                    },
                    "category": {"type": "string"},
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "question": {"type": "string"},
                    "decision": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["kind"],
            },
        }

    def _try_expand_skill(self, user_message: str, project_id: str | None) -> dict[str, Any] | None:
        text = user_message.strip()
        if not text.startswith("/"):
            return None

        parts = text[1:].split(" ", 1)
        name = parts[0].strip().lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        if not name:
            return None

        skill = self.skill_service.find_skill(name, project_id=project_id)
        if not skill:
            return None

        expanded = skill.prompt_template.replace("{args}", args)
        if args and "{args}" not in skill.prompt_template:
            expanded = f"{skill.prompt_template.rstrip()}\n\nArgs:\n{args}"
        return {
            "skill": skill,
            "expanded_prompt": expanded,
            "agent": skill.agent,
        }

    def _create_run_from_tool(
        self,
        *,
        thread_id: str,
        message_id: str,
        context: dict[str, Any],
        tool_input: dict[str, Any],
        fallback_user_message: str,
        agent_override: str | None,
        command: str | None,
        model: str | None,
        reasoning_effort: str | None,
        metadata: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        agent = agent_override or str(tool_input.get("agent") or settings.DEFAULT_RUN_AGENT)
        rationale = str(tool_input.get("rationale") or "").strip()
        task_description = str(tool_input.get("task_description") or "").strip() or fallback_user_message.strip()
        prompt = self._build_run_prompt(task_description, context, rationale=rationale)
        run = self.run_service.create_run(
            thread_id,
            {
                "agent": agent,
                "command": command,
                "prompt": prompt,
                "model": model,
                "reasoningEffort": reasoning_effort,
                "context": context,
                "metadata": {
                    **(metadata or {}),
                    "routedBy": "conversation-router",
                    "routerModel": settings.ANTHROPIC_MODEL,
                    "routerMode": "llm",
                    "routerRationale": rationale,
                },
            },
            message_id=message_id,
            auto_start=True,
        )
        return [run.to_dict(include_artifacts=False)] if run else []

    def _record_memory_from_tool(
        self,
        tool_input: dict[str, Any],
        *,
        thread_id: str,
        project_id: str | None,
    ) -> tuple[str, dict[str, Any]] | None:
        kind = str(tool_input.get("kind") or "").strip()
        if kind == "preference":
            key = str(tool_input.get("key") or "").strip()
            value = str(tool_input.get("value") or "").strip()
            if not key or not value:
                return None
            preference = self.memory_service.create_preference(
                {
                    "category": str(tool_input.get("category") or "general").strip() or "general",
                    "key": key,
                    "value": value,
                    "sourceThreadId": thread_id,
                }
            )
            return "preference", preference.to_dict()

        if kind == "decision" and project_id:
            decision = str(tool_input.get("decision") or "").strip()
            if not decision:
                return None
            record = self.memory_service.ensure_decision(
                {
                    "projectId": project_id,
                    "question": str(tool_input.get("question") or "本轮确认的方案").strip() or "本轮确认的方案",
                    "decision": decision,
                    "reasoning": str(tool_input.get("reasoning") or "").strip(),
                    "sourceThreadId": thread_id,
                }
            )
            return "decision", record.to_dict()

        if kind == "learning" and project_id:
            content = str(tool_input.get("content") or "").strip()
            learning = self.memory_service.ensure_learning(
                {
                    "projectId": project_id,
                    "content": content,
                    "sourceThreadId": thread_id,
                }
            )
            if learning:
                return "learning", learning.to_dict()
        return None

    def _create_runs_heuristically(
        self,
        *,
        thread_id: str,
        message_id: str,
        user_message: str,
        context: dict[str, Any],
        agent: str | None,
        command: str | None,
        model: str | None,
        reasoning_effort: str | None,
        metadata: dict[str, Any] | None,
        create_run: bool | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        should_run = create_run if create_run is not None else self._looks_like_execution(user_message)
        if not should_run:
            return [], None

        agents = self._resolve_agents(agent=agent, command=command, user_message=user_message)
        compare_group_id = str(uuid4()) if len(agents) > 1 else None
        runs: list[dict[str, Any]] = []
        for agent_spec in agents:
            run = self.run_service.create_run(
                thread_id,
                {
                    "agent": agent_spec.get("agent") or settings.DEFAULT_RUN_AGENT,
                    "command": agent_spec.get("command") or command,
                    "prompt": self._build_run_prompt(user_message, context),
                    "model": model or agent_spec.get("model"),
                    "reasoningEffort": reasoning_effort or agent_spec.get("reasoningEffort"),
                    "context": context,
                    "metadata": {
                        **(metadata or {}),
                        "routedBy": "conversation-router",
                        "routerMode": "heuristic",
                        **(
                            {
                                "compareGroupId": compare_group_id,
                                "compareLabel": agent_spec.get("label") or agent_spec.get("agent") or settings.DEFAULT_RUN_AGENT,
                                "comparePrompt": user_message.strip(),
                            }
                            if compare_group_id
                            else {}
                        ),
                    },
                },
                message_id=message_id,
                auto_start=True,
            )
            if run:
                runs.append(run.to_dict(include_artifacts=False))
        return runs, compare_group_id

    def _resolve_agents(self, *, agent: str | None, command: str | None, user_message: str) -> list[dict[str, Any]]:
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

    def _chunk_text(self, content: str, chunk_size: int = 36) -> list[str]:
        if not content:
            return []
        return [content[index:index + chunk_size] for index in range(0, len(content), chunk_size)]

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

    def _build_run_prompt(self, user_message: str, context: dict[str, Any], rationale: str = "") -> str:
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

        if rationale:
            lines.extend(["", "# Why This Run", rationale.strip()])

        history_text = str(context.get("historyText") or "").strip()
        if history_text:
            lines.extend(["", "# Thread History", history_text])

        if pinned_resources:
            lines.extend(
                [
                    "",
                    "# Pinned Resources",
                    *[
                        f"- [{resource.get('type')}] {resource.get('title') or resource.get('uri')}: {resource.get('uri')}"
                        for resource in pinned_resources[:8]
                    ],
                ]
            )

        if preferences:
            lines.extend(
                [
                    "",
                    "# Preferences",
                    *[
                        f"- {item.get('category')} / {item.get('key')}: {item.get('value')}"
                        for item in preferences[:8]
                    ],
                ]
            )

        if decisions:
            lines.extend(
                [
                    "",
                    "# Decisions",
                    *[
                        f"- {item.get('question')}: {item.get('decision')}"
                        for item in decisions[:5]
                    ],
                ]
            )

        if learnings:
            lines.extend(
                [
                    "",
                    "# Project Learnings",
                    *[
                        f"- {item.get('content')}"
                        for item in learnings[:5]
                    ],
                ]
            )

        return "\n".join(lines)

    def _build_fallback_reply(
        self,
        *,
        user_message: str,
        context: dict[str, Any],
        runs: list[dict[str, Any]],
        recorded_preferences: list[dict[str, Any]],
        recorded_decisions: list[dict[str, Any]],
        recorded_learnings: list[dict[str, Any]],
        router_mode: str,
    ) -> str:
        reply_lines = []
        context_summary = str(context.get("summary") or "").strip()
        if context_summary:
            reply_lines.append("我已经结合当前 Thread 历史理解你的需求。")

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
                    f"已基于当前 Thread 创建 1 个 {run.get('agent')} run，默认模型 {run.get('model') or '未指定'} / {run.get('reasoningEffort') or 'default'}。"
                )
            else:
                agents = "、".join(str(run.get("agent") or "") for run in runs)
                reply_lines.append(f"已并发创建 {len(runs)} 个 runs：{agents}。")
            if context_summary:
                reply_lines.append("我已自动组装当前 Project、最近 Thread 摘要、钉住资源、历史偏好和决策作为执行上下文。")
            if router_mode == "llm":
                reply_lines.append("本轮意图判断已优先使用 LLM 路由。")
        else:
            reply_lines.append("我已把这条消息记入当前 Thread。")
            if self._looks_like_execution(user_message):
                reply_lines.append("如果你希望我直接开跑，也可以显式要求创建 run。")

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
