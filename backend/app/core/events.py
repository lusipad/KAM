"""
KAM 进程内事件总线。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
import threading
from typing import Any


@dataclass(slots=True)
class EventSubscription:
    channel: str
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


class EventBus:
    def __init__(self):
        self._queues: dict[str, list[EventSubscription]] = defaultdict(list)
        self._lock = threading.RLock()

    async def subscribe(self, channel: str) -> EventSubscription:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        subscription = EventSubscription(
            channel=channel,
            queue=queue,
            loop=asyncio.get_running_loop(),
        )
        with self._lock:
            self._queues[channel].append(subscription)
        return subscription

    async def unsubscribe(self, subscription: EventSubscription):
        with self._lock:
            subscribers = self._queues.get(subscription.channel) or []
            self._queues[subscription.channel] = [
                item for item in subscribers if item is not subscription
            ]
            if not self._queues[subscription.channel]:
                self._queues.pop(subscription.channel, None)

    def publish(self, channel: str, event: dict[str, Any]):
        with self._lock:
            subscribers = list(self._queues.get(channel, []))
        for subscription in subscribers:
            subscription.loop.call_soon_threadsafe(self._enqueue, subscription.queue, event)

    @staticmethod
    def _enqueue(queue: asyncio.Queue, event: dict[str, Any]):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


event_bus = EventBus()
