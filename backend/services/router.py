from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Message, Thread, now
from services.context import ContextAssembler
from services.memory import MemoryService
from services.run_engine import RunEngine
from services.watcher import watcher_engine


SKILL_TEMPLATES = {
    "review-pr": "检查最新的 PR 评论，区分哪些需要用户决策、哪些可以由 AI 直接修复，并准备相应的修复或回复。",
    "commit": "检查当前工作树，暂存相关改动，创建一条干净的提交，并明确给出最终提交信息。",
}

TOOL_SCHEMAS = [
    {
        "name": "record_memory",
        "description": "记录稳定的偏好、决策、事实或经验，供后续对话与执行复用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["preference", "decision", "fact", "learning"]},
                "content": {"type": "string"},
                "rationale": {"type": "string"},
                "scope": {"type": "string", "enum": ["project", "global"]},
            },
            "required": ["category", "content"],
        },
    },
    {
        "name": "create_watcher",
        "description": "为 GitHub PR、CI 流水线或 Azure DevOps 任务创建持续监控。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "sourceType": {"type": "string", "enum": ["github_pr", "ci_pipeline", "azure_devops"]},
                "config": {"type": "object"},
                "scheduleType": {"type": "string", "enum": ["interval", "cron"]},
                "scheduleValue": {"type": "string"},
                "autoActionLevel": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["name", "sourceType", "config", "scheduleType", "scheduleValue"],
        },
    },
    {
        "name": "create_run",
        "description": "把实现、修复、部署、评审处理等具体工作下发给 agent 执行。",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "enum": ["codex", "claude-code", "custom"]},
                "task": {"type": "string"},
            },
            "required": ["agent", "task"],
        },
    },
]


@dataclass(slots=True)
class PlannedAction:
    tool: str
    input: dict[str, Any]


@dataclass(slots=True)
class OrchestrationPlan:
    assistant_reply: str
    actions: list[PlannedAction] = field(default_factory=list)


class ConversationRouter:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def route_message(self, *, thread_id: str, message_content: str, project_id: str | None) -> list[dict[str, Any]]:
        context = await ContextAssembler(self.db).build(thread_id=thread_id, project_id=project_id, query=message_content)
        resolved_project_id = project_id or getattr(context.get("thread"), "project_id", None)
        lower = message_content.lower()
        plan = await self._decide(message_content, context)
        actions = self._finalize_actions(plan.actions, lower)
        events: list[dict[str, Any]] = []

        for action in actions:
            result_event = await self._apply_action(action, thread_id=thread_id, project_id=resolved_project_id)
            if result_event is not None:
                events.append(result_event)

        reply = ""
        if actions == plan.actions:
            reply = plan.assistant_reply.strip()
        reply = reply or self._assistant_reply(actions=actions, context=context, lower=lower)
        await self._touch_thread(thread_id)
        for fragment in self._stream_text(reply):
            events.append({"type": "text_delta", "delta": fragment})
        events.append({"type": "text_done", "content": reply})
        return events

    async def _apply_action(
        self,
        action: PlannedAction,
        *,
        thread_id: str,
        project_id: str | None,
    ) -> dict[str, Any] | None:
        if action.tool == "record_memory":
            memory = await MemoryService(self.db).record(
                project_id=project_id,
                category=action.input["category"],
                content=action.input["content"],
                rationale=action.input.get("rationale"),
                scope=action.input.get("scope", "project"),
                source_thread_id=thread_id,
            )
            return {"type": "tool_result", "tool": "record_memory", "memory": memory.to_dict()}

        if action.tool == "create_watcher":
            if project_id is None:
                return None
            watcher = await watcher_engine.create_watcher(
                self.db,
                project_id=project_id,
                name=action.input["name"],
                source_type=action.input["sourceType"],
                config=action.input["config"],
                schedule_type=action.input["scheduleType"],
                schedule_value=action.input["scheduleValue"],
                auto_action_level=action.input.get("autoActionLevel", 1),
                status="draft",
            )
            self.db.add(
                Message(
                    thread_id=thread_id,
                    role="system",
                    content=f"已草拟监控 {watcher.name}，确认后启用。",
                    metadata_={"kind": "watcher-config", "watcher": watcher.to_dict()},
                )
            )
            await self.db.commit()
            return {"type": "tool_result", "tool": "create_watcher", "watcher": watcher.to_dict()}

        if action.tool == "create_run":
            run = await RunEngine(self.db).create_run(
                thread_id=thread_id,
                agent=action.input["agent"],
                task=action.input["task"],
            )
            return {"type": "tool_result", "tool": "create_run", "run": run.to_dict()}

        return None

    async def _touch_thread(self, thread_id: str) -> None:
        thread = await self.db.get(Thread, thread_id)
        if thread is not None:
            thread.updated_at = now()
            await self.db.commit()

    async def _decide(self, message_content: str, context: dict[str, Any]) -> OrchestrationPlan:
        fallback = self._fallback_plan(message_content, context)
        if self.client is None:
            return fallback

        prompt = (
            f"{context['prompt_context']}\n\n"
            "## 用户请求\n"
            f"{message_content.strip()}\n"
        )

        try:
            response = await self.client.messages.create(
                model=settings.chat_model,
                max_tokens=700,
                temperature=0,
                system=self._tool_system_prompt(),
                messages=[{"role": "user", "content": prompt}],
                tools=TOOL_SCHEMAS,
            )
        except Exception:
            return fallback

        return self._extract_plan_from_response(response, fallback)

    def _tool_system_prompt(self) -> str:
        return (
            "你是 KAM 的 orchestration core。你的目标是把用户输入转成最小且正确的后台动作。\n"
            "规则：\n"
            "1. 需要执行实现、修复、部署、评审处理时，调用 create_run。\n"
            "2. 用户表达稳定偏好、流程决策、长期事实或经验时，调用 record_memory。\n"
            "3. 用户要求持续监控时，调用 create_watcher。\n"
            "4. 可以连续调用多个工具；顺序就是实际执行顺序。\n"
            "5. 给用户的文字回复必须是简短中文，不暴露 JSON、schema 或内部推理。\n"
            "6. 如果只是继续解释、确认或承接上下文，可以不调用工具。"
        )

    def _extract_plan_from_response(self, response: Any, fallback: OrchestrationPlan) -> OrchestrationPlan:
        text_fragments: list[str] = []
        actions: list[PlannedAction] = []
        for block in getattr(response, "content", []):
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", "").strip()
                if text:
                    text_fragments.append(text)
                continue
            if block_type == "tool_use":
                action = self._normalize_model_action(getattr(block, "name", ""), getattr(block, "input", {}))
                if action is not None:
                    actions.append(action)

        text_reply = " ".join(fragment for fragment in text_fragments if fragment).strip()
        if not actions and text_reply.startswith("{") and text_reply.endswith("}"):
            legacy_plan = self._parse_legacy_json_plan(text_reply, fallback)
            if legacy_plan.actions or legacy_plan.assistant_reply:
                return legacy_plan

        if not actions and not text_reply:
            return fallback

        return OrchestrationPlan(
            assistant_reply=text_reply or fallback.assistant_reply,
            actions=self._dedupe_actions(actions or fallback.actions),
        )

    def _parse_legacy_json_plan(self, raw_text: str, fallback: OrchestrationPlan) -> OrchestrationPlan:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return fallback

        actions: list[PlannedAction] = []
        for memory_payload in payload.get("memories", []):
            action = self._normalize_model_action("record_memory", memory_payload)
            if action is not None:
                actions.append(action)
        if payload.get("watcher"):
            action = self._normalize_model_action("create_watcher", payload["watcher"])
            if action is not None:
                actions.append(action)
        if payload.get("run"):
            action = self._normalize_model_action("create_run", payload["run"])
            if action is not None:
                actions.append(action)

        reply = str(payload.get("assistantReply", "")).strip() or fallback.assistant_reply
        return OrchestrationPlan(assistant_reply=reply, actions=self._dedupe_actions(actions or fallback.actions))

    def _normalize_model_action(self, tool_name: str, payload: Any) -> PlannedAction | None:
        if not isinstance(payload, dict):
            return None

        if tool_name == "record_memory":
            category = str(payload.get("category", "")).strip().lower()
            content = str(payload.get("content", "")).strip()
            if category not in {"preference", "decision", "fact", "learning"} or not content:
                return None
            scope = str(payload.get("scope", "project")).strip().lower()
            if scope not in {"project", "global"}:
                scope = "project"
            rationale = str(payload.get("rationale", "")).strip() or None
            return PlannedAction(
                tool="record_memory",
                input={"category": category, "content": content, "rationale": rationale, "scope": scope},
            )

        if tool_name == "create_watcher":
            name = str(payload.get("name", "")).strip()
            source_type = str(payload.get("sourceType", "")).strip()
            config = payload.get("config")
            schedule_type = str(payload.get("scheduleType", "interval")).strip()
            schedule_value = str(payload.get("scheduleValue", "")).strip()
            if not name or source_type not in {"github_pr", "ci_pipeline", "azure_devops"}:
                return None
            if not isinstance(config, dict) or not schedule_value:
                return None
            if schedule_type not in {"interval", "cron"}:
                schedule_type = "interval"
            auto_action_level = self._coerce_auto_action_level(payload.get("autoActionLevel"))
            return PlannedAction(
                tool="create_watcher",
                input={
                    "name": name,
                    "sourceType": source_type,
                    "config": config,
                    "scheduleType": schedule_type,
                    "scheduleValue": schedule_value,
                    "autoActionLevel": auto_action_level,
                },
            )

        if tool_name == "create_run":
            agent = str(payload.get("agent", "")).strip().lower()
            task = str(payload.get("task", "")).strip()
            if agent not in {"codex", "claude-code", "custom"} or not task:
                return None
            return PlannedAction(tool="create_run", input={"agent": agent, "task": task})

        return None

    def _coerce_auto_action_level(self, value: Any) -> int:
        try:
            level = int(value)
        except (TypeError, ValueError):
            return 1
        return min(3, max(1, level))

    def _dedupe_actions(self, actions: list[PlannedAction]) -> list[PlannedAction]:
        seen: set[str] = set()
        deduped: list[PlannedAction] = []
        for action in actions:
            fingerprint = f"{action.tool}:{json.dumps(action.input, sort_keys=True, ensure_ascii=False)}"
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(action)
        return deduped

    def _fallback_plan(self, message_content: str, context: dict[str, Any]) -> OrchestrationPlan:
        text = " ".join(message_content.strip().split())
        lower = text.lower()
        skill_name, skill_args = self._extract_skill(text)

        actions: list[PlannedAction] = []
        memories = self._memory_payloads(text, lower)
        actions.extend(PlannedAction(tool="record_memory", input=payload) for payload in memories)

        watcher = self._watcher_payload(text, lower)
        if watcher:
            actions.append(PlannedAction(tool="create_watcher", input=watcher))

        run = self._run_payload(text, lower, context, skill_name, skill_args)
        if run:
            actions.append(PlannedAction(tool="create_run", input=run))

        reply = self._assistant_reply(actions=actions, context=context, lower=lower)
        return OrchestrationPlan(assistant_reply=reply, actions=self._finalize_actions(actions, lower))

    def _memory_payloads(self, text: str, lower: str) -> list[dict[str, str]]:
        if any(token in lower for token in {"decision:", "decide", "decision", "决定", "统一", "drop ", "不再兼容", "只走", "只保留"}):
            return [{"category": "decision", "content": text, "rationale": "来自明确的架构或流程决策。"}]
        if any(token in lower for token in {"always", "never", "prefer", "偏好", "以后都", "不要", "默认"}):
            return [{"category": "preference", "content": text, "rationale": "来自用户直接表达的偏好。"}]
        if any(token in lower for token in {"learned", "lesson", "发现", "经验", "教训"}):
            return [{"category": "learning", "content": text, "rationale": "来自明确说明的经验或教训。"}]
        if any(token in lower for token in {"fact:", "repo path", "branch is", "地址是", "位于"}):
            return [{"category": "fact", "content": text, "rationale": "作为稳定的项目上下文记录。"}]
        return []

    def _watcher_payload(self, text: str, lower: str) -> dict[str, Any] | None:
        if not any(token in lower for token in {"watch", "monitor", "watcher", "监控", "订阅", "keep an eye"}):
            return None

        if any(token in lower for token in {"azure", "devops", "work item", "board"}):
            source_type = "azure_devops"
        elif any(token in lower for token in {"ci", "workflow", "pipeline", "build", "github actions"}):
            source_type = "ci_pipeline"
        else:
            source_type = "github_pr"

        schedule_type, schedule_value = self._schedule_from(text, lower)
        config = self._watcher_config_from(text, source_type, lower)
        return {
            "name": self._watcher_name(text, source_type, config),
            "sourceType": source_type,
            "config": config,
            "scheduleType": schedule_type,
            "scheduleValue": schedule_value,
            "autoActionLevel": self._auto_action_level(lower),
        }

    def _run_payload(
        self,
        text: str,
        lower: str,
        context: dict[str, Any],
        skill_name: str | None,
        skill_args: str,
    ) -> dict[str, str] | None:
        if skill_name:
            return {
                "agent": self._agent_from_text(lower),
                "task": self._skill_task(skill_name, skill_args, context),
            }

        run_tokens = {
            "fix",
            "implement",
            "build",
            "debug",
            "refactor",
            "deploy",
            "review",
            "reply",
            "commit",
            "address",
            "repair",
            "修复",
            "实现",
            "重构",
            "部署",
            "检查",
            "回复",
            "提交",
            "处理",
        }
        if not any(token in lower for token in run_tokens):
            return None
        return {
            "agent": self._agent_from_text(lower),
            "task": self._run_task(text, context),
        }

    def _finalize_actions(self, actions: list[PlannedAction], lower: str) -> list[PlannedAction]:
        finalized = self._dedupe_actions(actions)
        has_watcher = any(action.tool == "create_watcher" for action in finalized)
        has_run = any(action.tool == "create_run" for action in finalized)
        if has_watcher and has_run and not self._should_start_run_with_watcher(lower):
            finalized = [action for action in finalized if action.tool != "create_run"]
        return finalized

    def _should_start_run_with_watcher(self, lower: str) -> bool:
        return any(
            token in lower
            for token in {
                "run now",
                "check now",
                "fix now",
                "right now",
                "立即处理",
                "马上处理",
                "立刻处理",
                "现在处理",
                "先检查",
                "先处理",
                "现在修",
                "立刻修",
                "马上修",
            }
        )

    def _watcher_config_from(self, text: str, source_type: str, lower: str) -> dict[str, Any]:
        repo_match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text)
        repo = repo_match.group(1) if repo_match else "owner/repo"
        number_match = re.search(r"#(\d+)", text)

        if source_type == "azure_devops":
            board_match = re.search(r'board\s+[\"“]?([^\"”]+)[\"”]?', text, re.IGNORECASE)
            board = board_match.group(1).strip() if board_match else "KAM"
            return {"project": board, "board": board, "watch": "assigned_work_items"}
        if source_type == "ci_pipeline":
            branch_match = re.search(r"(?:branch|on)\s+([A-Za-z0-9_.\\/-]+)", text, re.IGNORECASE)
            branch = branch_match.group(1) if branch_match else "main"
            return {"repo": repo, "provider": "github_actions", "branch": branch}
        if number_match:
            return {
                "repo": repo,
                "watch": "review_comments",
                "number": int(number_match.group(1)),
                "external_ref": {"type": "github_pr", "repo": repo, "number": int(number_match.group(1))},
            }
        if any(token in lower for token in {"review", "comment", "comments"}):
            return {"repo": repo, "watch": "review_comments"}
        return {"repo": repo, "watch": "assigned_prs", "filter_user": "me"}

    def _schedule_from(self, text: str, lower: str) -> tuple[str, str]:
        english = re.search(r"every\s+(\d+)\s*(m|min|mins|minute|minutes|h|hr|hour|hours)\b", lower)
        if english:
            amount = int(english.group(1))
            unit = english.group(2)
            return "interval", f"{amount}{'h' if unit.startswith('h') else 'm'}"

        chinese = re.search(r"每\s*(\d+)\s*(分钟|分|小时|时)", text)
        if chinese:
            amount = int(chinese.group(1))
            unit = chinese.group(2)
            return "interval", f"{amount}{'h' if unit in {'小时', '时'} else 'm'}"

        if "hourly" in lower or "每小时" in text:
            return "interval", "1h"
        if "daily" in lower or "每天" in text:
            return "interval", "24h"
        if "weekly" in lower or "每周" in text:
            return "interval", "168h"
        if "on push" in lower:
            return "interval", "5m"
        return "interval", "15m"

    def _auto_action_level(self, lower: str) -> int:
        if any(token in lower for token in {"fully automatic", "auto-run", "automatically act", "自动执行", "自动处理", "无需确认"}):
            return 3
        if any(token in lower for token in {"auto-fix", "auto fix", "自动修复", "自动回复", "draft reply"}):
            return 2
        return 1

    def _watcher_name(self, text: str, source_type: str, config: dict[str, Any]) -> str:
        if source_type == "ci_pipeline":
            return "CI 监控"
        if source_type == "azure_devops":
            return "DevOps 任务同步"
        number = config.get("number")
        if number:
            return f"PR #{number} 评审监控"
        return self._title_from(text, prefix="监控")

    def _title_from(self, text: str, prefix: str) -> str:
        compact = " ".join(text.split())
        return f"{prefix}: {compact[:96]}"

    def _extract_skill(self, text: str) -> tuple[str | None, str]:
        match = re.match(r"^/([a-z0-9-]+)\b\s*(.*)$", text, re.IGNORECASE)
        if not match:
            return None, ""
        return match.group(1).lower(), match.group(2).strip()

    def _skill_task(self, skill_name: str, skill_args: str, context: dict[str, Any]) -> str:
        base = SKILL_TEMPLATES.get(skill_name)
        if base is None:
            return self._run_task(f"执行 /{skill_name} 工作流。{skill_args}".strip(), context)
        if skill_args:
            return f"{base} 重点：{skill_args}"
        return base

    def _humanize_schedule_value(self, value: str) -> str:
        match = re.match(r"^(\d+)([mhd])$", value)
        if not match:
            return value
        amount = match.group(1)
        unit = match.group(2)
        label = "分钟" if unit == "m" else "小时" if unit == "h" else "天"
        return f"每 {amount} {label}"

    def _agent_from_text(self, lower: str) -> str:
        if "claude-code" in lower or "claude code" in lower or re.search(r"\bclaude\b", lower):
            return "claude-code"
        if "custom" in lower:
            return "custom"
        return "codex"

    def _run_task(self, text: str, context: dict[str, Any]) -> str:
        project = context.get("project")
        compact = text.strip()
        if project is not None and getattr(project, "title", None):
            return f"[{project.title}] {compact}"
        return compact

    def _assistant_reply(
        self,
        *,
        actions: list[PlannedAction],
        context: dict[str, Any],
        lower: str,
    ) -> str:
        run = next((action.input for action in actions if action.tool == "create_run"), None)
        watcher = next((action.input for action in actions if action.tool == "create_watcher"), None)
        memories = [action.input for action in actions if action.tool == "record_memory"]
        parts: list[str] = []
        if run:
            agent_label = "Claude Code" if run["agent"] == "claude-code" else "Codex"
            parts.append(f"我已经安排 {agent_label} 开始处理，结果会直接折回当前线程。")
        if watcher:
            schedule_label = self._humanize_schedule_value(watcher["scheduleValue"])
            parts.append(f"我先草拟了一个 {self._watcher_label(watcher['sourceType'])} 监控，频率是 {schedule_label}；你确认后我再启用。")
        if memories:
            categories = "、".join(self._memory_label(item["category"]) for item in memories)
            parts.append(f"同时记住这条{categories}。")
        if parts:
            memory_hint = self._memory_hint(context)
            if memory_hint:
                parts.append(f"我会继续沿用“{memory_hint}”。")
            return " ".join(parts)

        if self._is_continue_request(lower):
            continued = self._continue_reply(context)
            if continued:
                return continued

        if context.get("has_memory"):
            memory_hint = self._memory_hint(context)
            if memory_hint:
                return f"收到。我会沿用“{memory_hint}”继续判断，你可以直接让我实现、修复、监控或记录新的决定。"
            return "收到。我会沿用当前项目记忆继续判断，你可以直接让我实现、修复、监控或记录新的决定。"
        if context.get("has_recent_activity"):
            return "收到。我会接着这个线程最近的上下文继续，你可以直接给我要执行或监控的目标。"
        return "收到。你继续描述目标，我会把需要执行、监控或记录的部分直接转成后台动作。"

    def _watcher_label(self, source_type: str) -> str:
        if source_type == "ci_pipeline":
            return "CI"
        if source_type == "azure_devops":
            return "DevOps"
        return "GitHub"

    def _memory_label(self, category: str) -> str:
        labels = {
            "preference": "偏好",
            "decision": "决定",
            "learning": "经验",
            "fact": "事实",
        }
        return labels.get(category, "信息")

    def _is_continue_request(self, lower: str) -> bool:
        return any(token in lower for token in {"continue", "pick up", "继续", "接着", "昨天", "resume"})

    def _continue_reply(self, context: dict[str, Any]) -> str | None:
        thread = context.get("thread")
        if thread is None:
            return None

        latest_run = thread.runs[-1] if thread.runs else None
        latest_message = next(
            (
                message.content
                for message in reversed(thread.messages)
                if message.role in {"assistant", "system"} and (message.metadata_ or {}).get("kind") != "restore-summary"
            ),
            None,
        )
        if latest_run and latest_message:
            summary = latest_run.result_summary or latest_run.task
            return f"上次做到这里：{summary} 最近我还提到过“{latest_message[:80]}”。"
        if latest_run:
            summary = latest_run.result_summary or latest_run.task
            return f"上次做到这里：{summary}"
        if latest_message:
            return f"上次的上下文里，最近一条关键进展是“{latest_message[:120]}”。"
        return None

    def _memory_hint(self, context: dict[str, Any]) -> str | None:
        memory_pack = context.get("memory_pack") or {}
        for memory in memory_pack.get("always", []) + memory_pack.get("relevant", []):
            if getattr(memory, "content", None):
                return str(memory.content)[:120]
        memory_block = context.get("memory_block") or ""
        for line in memory_block.splitlines():
            if line.startswith("- ["):
                return line.split("] ", 1)[-1][:120]
        return None

    def _stream_text(self, content: str) -> list[str]:
        if len(content) <= 32:
            return [content]
        segments = []
        cursor = 0
        while cursor < len(content):
            segments.append(content[cursor : cursor + 24])
            cursor += 24
        return segments
