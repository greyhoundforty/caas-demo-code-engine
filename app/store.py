"""In-memory event feed with fan-out to SSE subscribers."""

import asyncio
import json
import uuid
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime


class EventStore:
    def __init__(self, max_events: int = 50):
        self._events: deque[dict] = deque(maxlen=max_events)
        self._subscribers: set[asyncio.Queue] = set()

    def add(self, event: dict) -> dict | None:
        """Store an event; return it, or None if its id is already in the buffer."""
        event = dict(event)
        if "id" in event and any(e["id"] == event["id"] for e in self._events):
            return None
        event.setdefault("id", uuid.uuid4().hex)
        event["ts"] = datetime.now(UTC).isoformat()
        self._events.append(event)
        for queue in self._subscribers:
            queue.put_nowait(event)
        return event

    def recent(self) -> list[dict]:
        return list(self._events)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)


def _frame(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def sse_stream(store: EventStore) -> AsyncIterator[str]:
    """Yield recent events, then live ones, as Server-Sent Event frames."""
    queue = store.subscribe()
    try:
        for event in store.recent():
            yield _frame(event)
        while True:
            yield _frame(await queue.get())
    finally:
        store.unsubscribe(queue)
