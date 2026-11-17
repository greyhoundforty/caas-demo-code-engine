import hashlib
import hmac

import pytest

from app.github import push_event, verify_signature

BODY = b'{"zen": "Keep it logically awesome."}'
SECRET = "s3cret"


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


PUSH = {
    "ref": "refs/heads/main",
    "repository": {"full_name": "greyhoundforty/caas-demo-code-engine"},
    "head_commit": {
        "id": "af363efb8568874fe219bc73f3bccd0f4991907f",
        "message": "Fix the thing\n\nLonger explanation here.",
        "url": "https://github.com/greyhoundforty/caas-demo-code-engine/commit/af363ef",
        "author": {"name": "Ryan Tiffany", "username": "greyhoundforty"},
    },
}


def test_verify_signature_ok():
    assert verify_signature(SECRET, BODY, sign(SECRET, BODY)) is True


def test_verify_signature_rejects_wrong_secret():
    assert verify_signature(SECRET, BODY, sign("other", BODY)) is False


def test_verify_signature_rejects_tampered_body():
    assert verify_signature(SECRET, BODY + b" ", sign(SECRET, BODY)) is False


@pytest.mark.parametrize("header", [None, "", "abc", "sha1=deadbeef", "sha256="])
def test_verify_signature_rejects_missing_or_malformed_header(header):
    assert verify_signature(SECRET, BODY, header) is False


def test_verify_signature_rejects_non_ascii_header_without_raising():
    assert verify_signature(SECRET, BODY, "sha256=caf\xe9") is False


def test_verify_signature_rejects_empty_secret():
    assert verify_signature("", BODY, sign("", BODY)) is False


def test_push_event_fields():
    assert push_event(PUSH) == {
        "kind": "push",
        "repo": "greyhoundforty/caas-demo-code-engine",
        "branch": "main",
        "author": "Ryan Tiffany",
        "message": "Fix the thing",
        "commit": "af363ef",
        "url": "https://github.com/greyhoundforty/caas-demo-code-engine/commit/af363ef",
    }


def test_push_event_multiline_message_uses_first_line():
    assert push_event(PUSH)["message"] == "Fix the thing"


def test_push_event_without_head_commit_does_not_crash():
    payload = {**PUSH, "head_commit": None, "deleted": True}
    event = push_event(payload)
    assert event["kind"] == "push"
    assert event["branch"] == "main"
    assert event["commit"] == ""
    assert event["message"] == ""
