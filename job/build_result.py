"""Validation and enrichment of build-result JSON documents."""

import json

REQUIRED_STRINGS = ("repo", "branch", "commit", "builder")
STATUSES = ("passed", "failed")


class Rejected(Exception):
    """The uploaded object is not a usable build result; str(self) is why."""


def decode(raw: bytes) -> object:
    if not raw.strip():
        raise Rejected("empty file")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Rejected("not valid UTF-8 text") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Rejected(
            f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from exc


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate(doc: object) -> dict:
    if not isinstance(doc, dict):
        raise Rejected("top-level JSON must be an object")
    for field in REQUIRED_STRINGS:
        if field not in doc:
            raise Rejected(f"missing field: {field}")
        if not isinstance(doc[field], str) or not doc[field]:
            raise Rejected(f"{field} must be a non-empty string")
    if "status" not in doc:
        raise Rejected("missing field: status")
    if doc["status"] not in STATUSES:
        raise Rejected("status must be 'passed' or 'failed'")
    if "duration_s" not in doc:
        raise Rejected("missing field: duration_s")
    if not _is_count(doc["duration_s"]):
        raise Rejected("duration_s must be a non-negative integer")
    if "tests" not in doc:
        raise Rejected("missing field: tests")
    tests = doc["tests"]
    if not (
        isinstance(tests, dict)
        and _is_count(tests.get("passed"))
        and _is_count(tests.get("failed"))
    ):
        raise Rejected("tests must be an object with integer passed and failed")
    return doc


def enrich(doc: dict, key: str, size: int) -> dict:
    passed = doc["tests"]["passed"]
    failed = doc["tests"]["failed"]
    total = passed + failed
    pass_rate = 100.0 if total == 0 else round(passed / total * 100, 1)
    return {
        "kind": "build",
        "status": doc["status"],
        "repo": doc["repo"],
        "branch": doc["branch"],
        "commit": doc["commit"],
        "duration_s": doc["duration_s"],
        "tests": {"passed": passed, "failed": failed},
        "builder": doc["builder"],
        "pass_rate": pass_rate,
        "summary": (
            f"{doc['repo']}@{doc['commit']} {doc['status']} in "
            f"{doc['duration_s']}s ({passed}/{total} tests)"
        ),
        "key": key,
        "size": size,
    }
