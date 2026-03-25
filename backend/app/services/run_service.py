"""
KAM v2 Run 服务
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation import Message, Run, Thread, ThreadRunArtifact
from app.services.memory_service import MemoryService
from app.services.run_engine import run_engine


class RunService:
    def __init__(self, db: Session):
        self.db = db

    def list_runs(self, thread_id: str) -> list[Run]:
        return self.db.query(Run).filter(Run.thread_id == thread_id).order_by(Run.created_at.desc()).all()

    def get_run(self, run_id: str) -> Run | None:
        return self.db.query(Run).filter(Run.id == run_id).first()

    def list_artifacts(self, run_id: str) -> list[ThreadRunArtifact]:
        return (
            self.db.query(ThreadRunArtifact)
            .filter(ThreadRunArtifact.run_id == run_id)
            .order_by(ThreadRunArtifact.created_at.asc())
            .all()
        )

    def hydrate_artifact(self, artifact: ThreadRunArtifact, max_chars: int | None = None) -> dict[str, Any]:
        payload = artifact.to_dict()
        content = payload.get("content") or ""
        if max_chars and len(content) > max_chars:
            payload["content"] = content[-max_chars:]
            payload["truncated"] = True
        else:
            payload["truncated"] = False
        return payload

    def create_run(self, thread_id: str, data: dict[str, Any], message_id: str | None = None, auto_start: bool = True) -> Run | None:
        thread = self.db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            return None

        agent = data.get("agent") or settings.DEFAULT_RUN_AGENT
        model = data.get("model")
        reasoning_effort = data.get("reasoningEffort") or data.get("reasoning_effort")
        if agent == "codex":
            model = model or settings.CODEX_MODEL
            reasoning_effort = reasoning_effort or settings.CODEX_REASONING_EFFORT

        work_dir = self._create_workdir(thread_id, agent)
        prompt = data.get("prompt") or self._resolve_message_prompt(message_id)
        message_id = self._ensure_run_message_id(thread, message_id, prompt, agent, data.get("metadata") or {})
        run = Run(
            thread_id=thread.id,
            message_id=message_id,
            agent=agent,
            model=model,
            reasoning_effort=reasoning_effort,
            command=data.get("command"),
            status="pending",
            work_dir=str(work_dir),
            round=1,
            max_rounds=data.get("maxRounds") or data.get("max_rounds") or 5,
            metadata_={
                "requestedAt": datetime.utcnow().isoformat(),
                **(data.get("metadata") or {}),
            },
        )
        self.db.add(run)
        self.db.flush()

        self._write_artifact(
            run,
            artifact_type="prompt",
            title=f"{agent} prompt",
            content=prompt,
            path=work_dir / "prompt.md",
        )
        context_payload = data.get("context") or self._build_context(thread)
        self._write_artifact(
            run,
            artifact_type="context",
            title="thread context",
            content=json.dumps(context_payload, ensure_ascii=False, indent=2),
            path=work_dir / "context.json",
        )

        thread.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(run)
        if auto_start:
            self.start_run(str(run.id))
            self.db.expire(run)
            self.db.refresh(run)
        return run

    def compare_runs(self, thread_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        thread = self.db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            return None

        prompt = str(data.get("prompt") or "").strip()
        raw_agents = data.get("agents") or []
        if not prompt or len(raw_agents) < 2:
            return None

        compare_id = str(data.get("compareId") or uuid4())
        auto_start = bool(data.get("autoStart", True))
        max_rounds = data.get("maxRounds") or data.get("max_rounds") or 5
        prepared_agents: list[dict[str, Any]] = []
        for index, agent_spec in enumerate(raw_agents, start=1):
            resolved_agent = agent_spec.get("agent") or settings.DEFAULT_RUN_AGENT
            label = str(agent_spec.get("label") or resolved_agent).strip() or f"方案 {index}"
            prepared_agents.append(
                {
                    "agent": resolved_agent,
                    "label": label,
                    "command": agent_spec.get("command"),
                    "model": agent_spec.get("model"),
                    "reasoningEffort": agent_spec.get("reasoningEffort") or agent_spec.get("reasoning_effort"),
                    "metadata": agent_spec.get("metadata") or {},
                }
            )

        message = Message(
            thread_id=thread.id,
            role="system",
            content=f"并发对比：{prompt}",
            metadata_={
                "eventType": "compare-created",
                "status": "pending",
                "compareGroupId": compare_id,
                "requestedAgents": prepared_agents,
            },
        )
        self.db.add(message)
        self.db.flush()

        runs: list[Run] = []
        for index, agent_spec in enumerate(prepared_agents, start=1):
            run = self.create_run(
                thread_id,
                {
                    "agent": agent_spec["agent"],
                    "command": agent_spec.get("command"),
                    "prompt": prompt,
                    "model": agent_spec.get("model"),
                    "reasoningEffort": agent_spec.get("reasoningEffort"),
                    "maxRounds": max_rounds,
                    "metadata": {
                        **(data.get("metadata") or {}),
                        **(agent_spec.get("metadata") or {}),
                        "compareGroupId": compare_id,
                        "compareLabel": agent_spec["label"],
                        "compareIndex": index,
                        "comparePrompt": prompt,
                        "compareRequestedAgents": prepared_agents,
                    },
                },
                message_id=str(message.id),
                auto_start=auto_start,
            )
            if run:
                runs.append(run)

        thread.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.expire(message)
        self.db.refresh(message)

        return {
            "compareId": compare_id,
            "threadId": str(thread.id),
            "prompt": prompt,
            "message": message.to_dict(include_runs=True),
            "requestedAgents": prepared_agents,
            "runs": [run.to_dict(include_artifacts=False) for run in runs],
        }

    def start_run(self, run_id: str) -> Run | None:
        run = self.get_run(run_id)
        if not run:
            return None
        launched = run_engine.launch_run(str(run.id))
        if launched:
            self.db.expire(run)
            self.db.refresh(run)
        return run

    def cancel_run(self, run_id: str) -> Run | None:
        run = self.get_run(run_id)
        if not run:
            return None
        if run.status in {"passed", "failed", "cancelled"}:
            return run

        run_engine.cancel_run(str(run.id))
        run.status = "cancelled"
        run.error = run.error or "Run 已取消"
        run.completed_at = datetime.utcnow()
        run.thread.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(run)
        return run

    def retry_run(self, run_id: str) -> Run | None:
        previous_run = self.get_run(run_id)
        if not previous_run:
            return None

        retry = self.create_run(
            str(previous_run.thread_id),
            {
                "agent": previous_run.agent,
                "model": previous_run.model,
                "reasoningEffort": previous_run.reasoning_effort,
                "command": previous_run.command,
                "prompt": self._artifact_content(previous_run, "prompt"),
                "maxRounds": previous_run.max_rounds,
                "metadata": {
                    **(previous_run.metadata_ or {}),
                    "retryOf": str(previous_run.id),
                },
            },
            message_id=str(previous_run.message_id) if previous_run.message_id else None,
            auto_start=False,
        )
        if retry:
            retry.round = (previous_run.round or 1) + 1
            self.db.commit()
            self.db.refresh(retry)
            self.start_run(str(retry.id))
            self.db.expire(retry)
            self.db.refresh(retry)
        return retry

    def adopt_run(self, run_id: str) -> Run | None:
        run = self.get_run(run_id)
        if not run:
            return None

        run.metadata_ = {
            **(run.metadata_ or {}),
            "adopted": True,
            "adoptedAt": datetime.utcnow().isoformat(),
        }
        if run.status == "pending":
            run.status = "passed"
            run.completed_at = run.completed_at or datetime.utcnow()
        run.thread.updated_at = datetime.utcnow()
        self.db.commit()

        self._record_adoption_memory(run)

        self.db.refresh(run)
        return run

    def _create_workdir(self, thread_id: str, agent: str) -> Path:
        safe_agent = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in agent.lower()).strip("-")
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        workdir = Path(settings.AGENT_WORKROOT) / "v2" / str(thread_id) / f"{safe_agent}-{timestamp}"
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def _resolve_message_prompt(self, message_id: str | None) -> str:
        if not message_id:
            return ""
        message = self.db.query(Message).filter(Message.id == message_id).first()
        return message.content if message else ""

    def _ensure_run_message_id(
        self,
        thread: Thread,
        message_id: str | None,
        prompt: str,
        agent: str,
        metadata: dict[str, Any],
    ) -> str | None:
        if message_id:
            return message_id

        snippet = (prompt or "").strip() or f"启动 {agent} run"
        snippet = snippet.replace("\n", " ").strip()
        if len(snippet) > 120:
            snippet = f"{snippet[:117]}..."
        message = Message(
            thread_id=thread.id,
            role="system",
            content=f"创建执行：{snippet}",
            metadata_={
                "eventType": "run-created",
                "status": "pending",
                "agent": agent,
                **({"compareGroupId": metadata.get("compareGroupId")} if metadata.get("compareGroupId") else {}),
            },
        )
        self.db.add(message)
        self.db.flush()
        return str(message.id)

    def _build_context(self, thread: Thread) -> dict[str, Any]:
        recent_messages = [message.to_dict() for message in (thread.messages or [])[-10:]]
        return {
            "thread": thread.to_dict(include_relations=False),
            "project": thread.project.to_dict(include_relations=False) if thread.project else None,
            "recentMessages": recent_messages,
        }

    def _write_artifact(self, run: Run, artifact_type: str, title: str, content: str, path: Path | None = None):
        artifact = ThreadRunArtifact(
            run_id=run.id,
            artifact_type=artifact_type,
            title=title,
            content=content,
            path=str(path) if path else None,
            round=run.round or 1,
        )
        self.db.add(artifact)
        if path is not None:
            path.write_text(content, encoding="utf-8")

    def _artifact_content(self, run: Run, artifact_type: str) -> str:
        for artifact in run.artifacts or []:
            if artifact.artifact_type == artifact_type:
                return artifact.content
        return ""

    def _record_adoption_memory(self, run: Run) -> None:
        compare_group_id = (run.metadata_ or {}).get("compareGroupId")
        compare_prompt = str((run.metadata_ or {}).get("comparePrompt") or "").strip()
        compare_label = str((run.metadata_ or {}).get("compareLabel") or run.agent).strip()
        if not compare_group_id or not compare_prompt or not run.thread.project_id:
            return

        summary = " ".join(self._artifact_content(run, "summary").strip().split())
        reasoning = f"用户在 Compare 中采纳了方案：{compare_label}。"
        if summary:
            reasoning = f"{reasoning} 结果摘要：{summary[:240]}"

        MemoryService(self.db).ensure_decision(
            {
                "projectId": str(run.thread.project_id),
                "question": compare_prompt,
                "decision": compare_label,
                "reasoning": reasoning,
                "sourceThreadId": str(run.thread_id),
            }
        )
