import asyncio
import hashlib
import hmac
import importlib
import json

import pytest
from starlette.testclient import TestClient

import app.main
from app.main import create_app
from app.store import EventStore

TOKEN = "tok"
SECRET = "sec"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BUILD = {"kind": "build", "id": "evt-1", "status": "passed", "summary": "ok"}
PUSH = {
    "ref": "refs/heads/main",
    "repository": {"full_name": "greyhoundforty/caas-demo-code-engine"},
    "head_commit": {
        "id": "af363efb8568874fe219bc73f3bccd0f4991907f",
        "message": "Fix",
        "url": "https://example.test/c/af363ef",
        "author": {"name": "Ryan"},
    },
}


@pytest.fixture
def store():
    return EventStore()


@pytest.fixture
def client(store):
    return TestClient(create_app(store, TOKEN, SECRET))


def signed(body: bytes, secret: str = SECRET) -> dict:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}"}


def webhook_status(client, body: bytes, headers: dict) -> int:
    return client.post("/webhook/github", content=body, headers=headers).status_code


def test_healthz(client):
    assert client.get("/healthz").status_code == 200


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "EventSource" in resp.text


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer nope"}, {"Authorization": TOKEN}],
)
def test_ingest_requires_token(client, store, headers):
    resp = client.post("/api/events", json=BUILD, headers=headers)
    assert resp.status_code == 401
    assert store.recent() == []


def test_ingest_accepts_valid_event(client, store):
    resp = client.post("/api/events", json=BUILD, headers=AUTH)
    assert resp.status_code == 201
    assert resp.json()["id"] == "evt-1"
    assert [e["id"] for e in store.recent()] == ["evt-1"]


@pytest.mark.parametrize("body", [b"[]", b"3", b"not json"])
def test_ingest_rejects_non_object_body(client, store, body):
    resp = client.post("/api/events", content=body, headers=AUTH)
    assert resp.status_code == 400
    assert store.recent() == []


def test_ingest_dedup_returns_200(client, store):
    client.post("/api/events", json=BUILD, headers=AUTH)
    resp = client.post("/api/events", json=BUILD, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"duplicate": True}
    assert len(store.recent()) == 1


def test_webhook_bad_signature_401_and_nothing_added(client, store):
    body = json.dumps(PUSH).encode()
    wrong = {**signed(body, "wrong"), "X-GitHub-Event": "push"}
    assert webhook_status(client, body, wrong) == 401
    assert webhook_status(client, body, {"X-GitHub-Event": "push"}) == 401
    assert store.recent() == []


def test_webhook_ignores_non_push(client, store):
    body = b'{"action": "opened"}'
    headers = {**signed(body), "X-GitHub-Event": "issues"}
    resp = client.post("/webhook/github", content=body, headers=headers)
    assert resp.status_code == 202
    assert resp.json() == {"ignored": "issues"}
    assert store.recent() == []


def test_webhook_ping_adds_nothing(client, store):
    body = b'{"zen": "hi"}'
    headers = {**signed(body), "X-GitHub-Event": "ping"}
    assert webhook_status(client, body, headers) == 200
    assert store.recent() == []


def test_webhook_push_adds_card(client, store):
    body = json.dumps(PUSH).encode()
    headers = {**signed(body), "X-GitHub-Event": "push"}
    resp = client.post("/webhook/github", content=body, headers=headers)
    assert resp.status_code == 201
    [event] = store.recent()
    assert event["kind"] == "push"
    assert event["commit"] == "af363ef"


def test_webhook_push_with_bad_json_is_400(client, store):
    body = b"not json"
    headers = {**signed(body), "X-GitHub-Event": "push"}
    assert webhook_status(client, body, headers) == 400
    assert store.recent() == []


async def test_events_route_streams_sse_with_replay(store):
    store.add({"id": "old", "kind": "push"})
    application = create_app(store, TOKEN, SECRET)
    sent: list[dict] = []

    async def receive():
        await asyncio.sleep(3600)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/events",
        "raw_path": b"/events",
        "query_string": b"",
        "headers": [],
        "http_version": "1.1",
        "scheme": "http",
        "server": ("test", 80),
    }
    task = asyncio.ensure_future(application(scope, receive, send))
    await asyncio.sleep(0.2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    start = sent[0]
    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    assert start["status"] == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache"
    assert headers["x-accel-buffering"] == "no"
    assert b'"id": "old"' in sent[1]["body"]
    assert len(store._subscribers) == 0


def test_module_refuses_empty_secrets(monkeypatch):
    with monkeypatch.context() as m:
        m.setenv("INGEST_TOKEN", "")
        with pytest.raises(RuntimeError):
            importlib.reload(app.main)
    importlib.reload(app.main)
