from __future__ import annotations

from typing import Any, Awaitable, Callable

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adapters import ADAPTERS
from db import async_session
from events import event_bus
from models import Message, Thread, Watcher, WatcherEvent, now
from services.action import ActionEngine
from services.digest import DigestService
from services.memory import MemoryService


_scheduler = None


def set_scheduler(scheduler) -> None:
    global _scheduler
    _scheduler = scheduler


class WatcherEngine:
    async def bootstrap(self) -> None:
        if _scheduler is None:
            return
        async with async_session() as session:
            result = await session.execute(select(Watcher).where(Watcher.status == "active"))
            watchers = list(result.scalars())
        for watcher in watchers:
            self._schedule(watcher)

    def schedule_memory_decay(self, callback: Callable[[], Awaitable[None]]) -> None:
        if _scheduler is None or _scheduler.get_job("memory-decay"):
            return
        _scheduler.add_job(callback, trigger=CronTrigger(hour=3), id="memory-decay", replace_existing=True)

    async def create_watcher(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        name: str,
        source_type: str,
        config: dict[str, Any],
        schedule_type: str,
        schedule_value: str,
        auto_action_level: int = 1,
    ) -> Watcher:
        watcher = Watcher(
            project_id=project_id,
            name=name,
            source_type=source_type,
            config=config,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            auto_action_level=auto_action_level,
        )
        db.add(watcher)
        await db.commit()
        await db.refresh(watcher)
        self._schedule(watcher)
        return watcher

    async def list_watchers(self, db: AsyncSession) -> list[Watcher]:
        result = await db.execute(select(Watcher).order_by(desc(Watcher.created_at)))
        return list(result.scalars())

    async def pause(self, db: AsyncSession, watcher_id: str) -> Watcher | None:
        watcher = await db.get(Watcher, watcher_id)
        if watcher is None:
            return None
        watcher.status = "paused"
        await db.commit()
        if _scheduler is not None:
            _scheduler.pause_job(f"watcher:{watcher_id}")
        return watcher

    async def resume(self, db: AsyncSession, watcher_id: str) -> Watcher | None:
        watcher = await db.get(Watcher, watcher_id)
        if watcher is None:
            return None
        watcher.status = "active"
        await db.commit()
        self._schedule(watcher)
        return watcher

    async def run_now(self, db: AsyncSession, watcher_id: str) -> WatcherEvent | None:
        await self.execute_watcher(watcher_id)
        result = await db.execute(
            select(WatcherEvent).where(WatcherEvent.watcher_id == watcher_id).order_by(desc(WatcherEvent.created_at)).limit(1)
        )
        return result.scalars().first()

    async def execute_watcher(self, watcher_id: str) -> None:
        async with async_session() as session:
            watcher = await session.get(Watcher, watcher_id)
            if watcher is None or watcher.status != "active":
                return
            adapter_cls = ADAPTERS.get(watcher.source_type)
            if adapter_cls is None:
                return
            adapter = adapter_cls()
            current = await adapter.fetch(watcher.config)
            changes = adapter.diff(watcher.last_state, current)
            watcher.last_state = current
            watcher.last_run_at = now()

            event = None
            has_changes = bool(changes.get("created") or changes.get("updated") or changes.get("review_comments"))
            if has_changes:
                summary = await DigestService(session).summarize_watcher_event(watcher, changes)
                thread = await self._ensure_thread(session, watcher, changes)
                actions = adapter.recommended_actions({"name": watcher.name, "config": watcher.config}, changes)
                event = WatcherEvent(
                    watcher_id=watcher.id,
                    thread_id=thread.id if thread else None,
                    event_type=self._event_type_for(watcher, changes),
                    title=self._title_for(watcher, changes),
                    summary=summary,
                    raw_data={"current": current, "changes": changes},
                    actions=actions,
                )
                session.add(event)
                await session.flush()
                if watcher.source_type == "github_pr" and changes.get("review_comments") and thread is not None:
                    cards = await DigestService(session).triage_pr_comments(
                        changes["review_comments"],
                        await MemoryService(session).build_context_block(watcher.project_id),
                    )
                    session.add(
                        Message(
                            thread_id=thread.id,
                            role="assistant",
                            content=f"{len(cards)} 条新的 review comment 已完成分流。",
                            metadata_={"kind": "review-triage", "eventId": event.id, "cards": cards},
                        )
                    )
                    thread.updated_at = now()

            await session.commit()

            if event is not None:
                await event_bus.publish("home", {"type": "watcher_event", "eventId": event.id, "watcherId": watcher.id})
                if event.thread_id:
                    await event_bus.publish(
                        f"thread:{event.thread_id}",
                        {"type": "watcher_event", "eventId": event.id, "watcherId": watcher.id},
                    )
                if watcher.auto_action_level >= 2 and event.actions:
                    await ActionEngine(session).execute(event, event.actions[0])

    async def execute_action(self, db: AsyncSession, event_id: str, action_index: int) -> dict[str, Any]:
        stmt = (
            select(WatcherEvent)
            .where(WatcherEvent.id == event_id)
            .options(selectinload(WatcherEvent.watcher))
        )
        result = await db.execute(stmt)
        event = result.scalars().first()
        if event is None:
            return {"ok": False, "error": "event_not_found"}
        actions = event.actions or []
        if action_index < 0 or action_index >= len(actions):
            return {"ok": False, "error": "invalid_action_index"}
        outcome = await ActionEngine(db).execute(event, actions[action_index])
        if outcome.get("ok"):
            event.status = "handled"
            await db.commit()
        return outcome

    async def dismiss_event(self, db: AsyncSession, event_id: str) -> WatcherEvent | None:
        event = await db.get(WatcherEvent, event_id)
        if event is None:
            return None
        event.status = "dismissed"
        await db.commit()
        return event

    def _schedule(self, watcher: Watcher) -> None:
        if _scheduler is None:
            return
        trigger = self._trigger_for(watcher.schedule_type, watcher.schedule_value)
        _scheduler.add_job(
            self.execute_watcher,
            trigger=trigger,
            args=[watcher.id],
            id=f"watcher:{watcher.id}",
            replace_existing=True,
        )

    def _trigger_for(self, schedule_type: str, schedule_value: str):
        if schedule_type == "cron":
            return CronTrigger.from_crontab(schedule_value)
        interval = self._parse_interval(schedule_value)
        return IntervalTrigger(seconds=interval)

    def _parse_interval(self, value: str) -> int:
        if value.endswith("m"):
            return int(value[:-1]) * 60
        if value.endswith("h"):
            return int(value[:-1]) * 3600
        return int(value)

    async def _ensure_thread(self, db: AsyncSession, watcher: Watcher, changes: dict[str, Any]) -> Thread | None:
        external_ref = watcher.config.get("external_ref")
        if external_ref:
            result = await db.execute(select(Thread).where(Thread.external_ref == external_ref))
            thread = result.scalars().first()
            if thread is not None:
                return thread
        created = changes.get("created", [])
        title = watcher.name
        if created:
            first = created[0]
            title = first.get("title") or first.get("body") or watcher.name
        thread = Thread(project_id=watcher.project_id, title=title[:180], external_ref=external_ref)
        db.add(thread)
        await db.flush()
        return thread

    def _event_type_for(self, watcher: Watcher, changes: dict[str, Any]) -> str:
        if watcher.source_type == "ci_pipeline":
            return "ci_failed"
        if changes.get("review_comments"):
            return "new_pr_comments"
        return "watcher_update"

    def _title_for(self, watcher: Watcher, changes: dict[str, Any]) -> str:
        if watcher.source_type == "ci_pipeline" and changes.get("created"):
            item = changes["created"][0]
            return f"CI failed on {item.get('head_branch', 'default')}"
        created = len(changes.get("created", []))
        updated = len(changes.get("updated", []))
        return f"{watcher.name}: {created} new, {updated} updated"


watcher_engine = WatcherEngine()
