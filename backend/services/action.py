from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from adapters import ADAPTERS
from models import Watcher, WatcherEvent
from services.run_engine import RunEngine


class ActionEngine:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, event: WatcherEvent, action: dict[str, Any]) -> dict[str, Any]:
        kind = action.get("kind")
        params = action.get("params", {})
        if kind == "create_run":
            run = await RunEngine(self.db).create_run(
                thread_id=event.thread_id,
                agent=params.get("agent", "codex"),
                task=params["task"],
            )
            return {"ok": True, "runId": run.id}

        watcher = event.watcher if getattr(event, "watcher", None) is not None else await self.db.get(Watcher, event.watcher_id)
        if watcher is None:
            return {"ok": False, "error": "watcher_not_found"}
        adapter_cls = ADAPTERS.get(watcher.source_type)
        if adapter_cls is None:
            return {"ok": False, "error": f"unsupported_source_type:{watcher.source_type}"}
        adapter = adapter_cls()
        return await adapter.perform(action)
