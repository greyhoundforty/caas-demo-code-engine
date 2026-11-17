import asyncio
import json
from datetime import datetime

from app.store import EventStore, sse_stream


def test_add_assigns_id_and_ts():
    store = EventStore()
    stored = store.add({"kind": "push"})
    assert stored["kind"] == "push"
    assert len(stored["id"]) == 32
    assert datetime.fromisoformat(stored["ts"]).tzinfo is not None
    assert store.recent() == [stored]


def test_add_keeps_caller_id():
    store = EventStore()
    assert store.add({"id": "evt-1", "kind": "build"})["id"] == "evt-1"


def test_add_dedups_by_id():
    store = EventStore()
    assert store.add({"id": "evt-1", "kind": "build"}) is not None
    assert store.add({"id": "evt-1", "kind": "build"}) is None
    assert len(store.recent()) == 1


def test_buffer_caps_at_max_events():
    store = EventStore(max_events=3)
    for i in range(5):
        store.add({"id": f"e{i}"})
    assert [e["id"] for e in store.recent()] == ["e2", "e3", "e4"]


async def test_subscriber_receives_new_event():
    store = EventStore()
    q = store.subscribe()
    stored = store.add({"kind": "push"})
    assert await asyncio.wait_for(q.get(), 1) == stored
    store.unsubscribe(q)
    store.add({"kind": "push"})
    assert q.empty()


async def test_sse_stream_replays_then_streams():
    store = EventStore()
    first = store.add({"id": "old", "kind": "push"})
    stream = sse_stream(store)
    frame = await asyncio.wait_for(anext(stream), 1)
    assert frame == f"data: {json.dumps(first)}\n\n"
    live = store.add({"id": "new", "kind": "build"})
    frame = await asyncio.wait_for(anext(stream), 1)
    assert frame == f"data: {json.dumps(live)}\n\n"
    await stream.aclose()


async def test_sse_stream_unsubscribes_on_close():
    store = EventStore()
    stream = sse_stream(store)
    task = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)
    assert len(store._subscribers) == 1
    store.add({"kind": "push"})
    await asyncio.wait_for(task, 1)
    await stream.aclose()
    assert len(store._subscribers) == 0
