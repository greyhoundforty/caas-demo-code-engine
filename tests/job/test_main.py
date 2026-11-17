import json

import httpx
import pytest

from job.build_result import Rejected
from job.main import (
    DEFAULT_COS_ENDPOINT,
    build_event,
    fetch_object,
    main,
    make_cos,
    parse_ce_data,
    post_event,
)

GOOD = {
    "repo": "caas-demo",
    "branch": "main",
    "commit": "a1b2c3d",
    "status": "passed",
    "duration_s": 74,
    "tests": {"passed": 128, "failed": 0},
    "builder": "tekton",
}

CE_DATA = (
    '{"bucket":"mybucket","endpoint":"","key":"incoming/Notes.json",'
    '"notification":{"bucket_name":"mybucket","event_type":"Object:Write",'
    '"format":"2.0","object_length":"4642","object_name":"incoming/Notes.json",'
    '"request_id":"r1","request_time":"2021-04-13T19:43:36.610Z"},'
    '"operation":"Object:Write"}'
)


class FakeBody:
    def __init__(self, data: bytes):
        self._data = data
        self.read_sizes: list[int | None] = []

    def read(self, amt=None):
        self.read_sizes.append(amt)
        return self._data if amt is None else self._data[:amt]


class FakeCos:
    def __init__(self, data: bytes, content_length: int | None = ...):
        self.body = FakeBody(data)
        self.content_length = len(data) if content_length is ... else content_length
        self.calls: list[tuple[str, str]] = []

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 signature
        self.calls.append((Bucket, Key))
        resp = {"Body": self.body}
        if self.content_length is not None:
            resp["ContentLength"] = self.content_length
        return resp


def env(operation_data: str = CE_DATA, **extra) -> dict:
    return {
        "CE_ID": "evt-1",
        "CE_DATA": operation_data,
        "INGEST_URL": "http://app.local/api/events",
        "INGEST_TOKEN": "t",
        **extra,
    }


def test_parse_ce_data():
    assert parse_ce_data(env()) == (
        "evt-1",
        "Object:Write",
        "mybucket",
        "incoming/Notes.json",
    )


def test_fetch_rejects_oversize_by_content_length():
    cos = FakeCos(b"x" * 70000)
    with pytest.raises(Rejected, match="64 KiB"):
        fetch_object(cos, "b", "k")
    assert cos.body.read_sizes == []


def test_fetch_rejects_oversize_without_content_length():
    cos = FakeCos(b"x" * 70000, content_length=None)
    with pytest.raises(Rejected, match="64 KiB"):
        fetch_object(cos, "b", "k")
    assert cos.body.read_sizes == [65537]


def test_fetch_returns_bytes_and_size():
    cos = FakeCos(b'{"a": 1}')
    assert fetch_object(cos, "b", "k") == (b'{"a": 1}', 8)
    assert cos.calls == [("b", "k")]


def test_build_event_valid():
    raw = json.dumps(GOOD).encode()
    event = build_event("evt-1", "incoming/x.json", raw, len(raw))
    assert event["kind"] == "build"
    assert event["id"] == "evt-1"
    assert event["summary"].startswith("caas-demo@a1b2c3d passed")


def test_build_event_rejected_keeps_id():
    event = build_event("evt-2", "incoming/x.json", b'{"repo": ', 9)
    assert event["kind"] == "rejected"
    assert event["id"] == "evt-2"
    assert event["key"] == "incoming/x.json"
    assert "invalid JSON" in event["reason"]


def test_post_event_sends_bearer_and_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    post_event({"kind": "build"}, "http://app.local/api/events", "t", client)
    assert seen == {
        "auth": "Bearer t",
        "url": "http://app.local/api/events",
        "body": {"kind": "build"},
    }


def test_main_posts_enriched_event():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={})

    cos = FakeCos(json.dumps(GOOD).encode())
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert main(env(), cos=cos, client=client) == 0
    assert seen["auth"] == "Bearer t"
    assert seen["body"]["kind"] == "build"
    assert seen["body"]["id"] == "evt-1"
    assert seen["body"]["key"] == "incoming/Notes.json"
    assert cos.calls == [("mybucket", "incoming/Notes.json")]


def test_main_posts_rejected_for_oversize_object():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert main(env(), cos=FakeCos(b"x" * 70000), client=client) == 0
    assert seen["body"]["kind"] == "rejected"
    assert "64 KiB" in seen["body"]["reason"]


def test_main_ignores_delete():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call expected")

    data = CE_DATA.replace("Object:Write", "Object:Delete")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    cos = FakeCos(b"")
    assert main(env(data), cos=cos, client=client) == 0
    assert cos.calls == []


def test_main_returns_1_on_500():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    cos = FakeCos(json.dumps(GOOD).encode())
    assert main(env(), cos=cos, client=client) == 1


def test_make_cos_uses_direct_endpoint_by_default():
    cos = make_cos({"COS_APIKEY": "k", "COS_RESOURCE_INSTANCE_ID": "crn:x"})
    assert cos.meta.endpoint_url == DEFAULT_COS_ENDPOINT
    assert DEFAULT_COS_ENDPOINT == (
        "https://s3.direct.ca-tor.cloud-object-storage.appdomain.cloud"
    )
