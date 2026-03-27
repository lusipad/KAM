from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._topics: defaultdict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._topics[topic].add(queue)
        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            if topic in self._topics:
                self._topics[topic].discard(queue)
                if not self._topics[topic]:
                    self._topics.pop(topic, None)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._topics.get(topic, set()))
        for queue in queues:
            await queue.put(dict(event))


event_bus = EventBus()
