"""GitHub webhook helpers: signature verification and push-event mapping."""

import hashlib
import hmac

SIGNATURE_PREFIX = "sha256="


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Check an X-Hub-Signature-256 header against the raw request body."""
    if not secret or not header or not header.startswith(SIGNATURE_PREFIX):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(SIGNATURE_PREFIX + expected, header)


def push_event(payload: dict) -> dict:
    """Map a GitHub push payload to a feed event."""
    head = payload.get("head_commit") or {}
    return {
        "kind": "push",
        "repo": payload["repository"]["full_name"],
        "branch": payload["ref"].removeprefix("refs/heads/"),
        "author": (head.get("author") or {}).get("name", ""),
        "message": head.get("message", "").split("\n", 1)[0],
        "commit": head.get("id", "")[:7],
        "url": head.get("url", ""),
    }
