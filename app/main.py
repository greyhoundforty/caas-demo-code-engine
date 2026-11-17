"""Build-event feed: ingest endpoint, GitHub webhook and SSE stream."""

import hmac
import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from starlette.routing import Route

from app.github import push_event, verify_signature
from app.store import EventStore, sse_stream

INDEX = Path(__file__).parent / "static" / "index.html"


async def _json_object(request: Request) -> dict | None:
    try:
        data = json.loads(await request.body())
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def create_app(store: EventStore, ingest_token: str, webhook_secret: str) -> Starlette:
    async def index(request: Request):
        return FileResponse(INDEX, media_type="text/html")

    async def healthz(request: Request):
        return PlainTextResponse("ok")

    async def events(request: Request):
        return StreamingResponse(
            sse_stream(store),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def ingest(request: Request):
        sent = request.headers.get("authorization", "")
        # Compare bytes: compare_digest raises TypeError on non-ASCII str input.
        if not hmac.compare_digest(sent.encode(), f"Bearer {ingest_token}".encode()):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        event = await _json_object(request)
        if event is None:
            return JSONResponse({"error": "body must be a JSON object"}, 400)
        stored = store.add(event)
        if stored is None:
            return JSONResponse({"duplicate": True}, status_code=200)
        return JSONResponse(stored, status_code=201)

    async def github_webhook(request: Request):
        body = await request.body()
        signature = request.headers.get("x-hub-signature-256")
        if not verify_signature(webhook_secret, body, signature):
            return JSONResponse({"error": "bad signature"}, status_code=401)
        kind = request.headers.get("x-github-event", "")
        if kind == "ping":
            return JSONResponse({"pong": True}, status_code=200)
        if kind != "push":
            return JSONResponse({"ignored": kind}, status_code=202)
        payload = await _json_object(request)
        try:
            event = push_event(payload or {})
        except (KeyError, TypeError, AttributeError):
            return JSONResponse({"error": "unrecognised push payload"}, 400)
        stored = store.add(event)
        return JSONResponse(stored, status_code=201)

    return Starlette(
        routes=[
            Route("/", index),
            Route("/healthz", healthz),
            Route("/events", events),
            Route("/api/events", ingest, methods=["POST"]),
            Route("/webhook/github", github_webhook, methods=["POST"]),
        ]
    )


def _from_env() -> Starlette:
    token = os.environ.get("INGEST_TOKEN", "")
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not token or not secret:
        raise RuntimeError("INGEST_TOKEN and WEBHOOK_SECRET must be set")
    return create_app(EventStore(), token, secret)


app = _from_env()
