import copy

import pytest

from job.build_result import Rejected, decode, enrich, validate

GOOD = {
    "repo": "caas-demo",
    "branch": "main",
    "commit": "a1b2c3d",
    "status": "passed",
    "duration_s": 74,
    "tests": {"passed": 128, "failed": 0},
    "builder": "tekton",
}

REQUIRED = ["repo", "branch", "commit", "status", "duration_s", "tests", "builder"]


def test_validate_accepts_sample():
    assert validate(copy.deepcopy(GOOD)) == GOOD


@pytest.mark.parametrize("doc", [[], 3, "x", None])
def test_validate_rejects_non_object(doc):
    with pytest.raises(Rejected):
        validate(doc)


def test_validate_rejects_bad_status():
    doc = {**GOOD, "status": "meh"}
    with pytest.raises(Rejected, match="status"):
        validate(doc)


@pytest.mark.parametrize("field", REQUIRED)
def test_validate_rejects_missing_field(field):
    doc = {k: v for k, v in GOOD.items() if k != field}
    with pytest.raises(Rejected, match=field):
        validate(doc)


@pytest.mark.parametrize("raw", [b"", b"\xff\xfe", b'{"repo": '])
def test_decode_rejects_empty_and_binary(raw):
    with pytest.raises(Rejected):
        decode(raw)


def test_decode_reports_line_and_column_of_the_error():
    with pytest.raises(Rejected, match=r"invalid JSON: .*\(line 2, column 7\)"):
        decode(b'{\n  "a" 1}')


def test_decode_returns_parsed_json():
    assert decode(b'{"a": 1}') == {"a": 1}


def test_enrich_pass_rate():
    doc = {**GOOD, "tests": {"passed": 128, "failed": 2}}
    assert enrich(doc, "incoming/x.json", 10)["pass_rate"] == 98.5
    doc = {**GOOD, "tests": {"passed": 0, "failed": 0}}
    assert enrich(doc, "incoming/x.json", 10)["pass_rate"] == 100.0


def test_enrich_summary_mentions_repo_and_status():
    event = enrich(GOOD, "incoming/x.json", 123)
    assert event["kind"] == "build"
    assert event["summary"] == "caas-demo@a1b2c3d passed in 74s (128/128 tests)"
    assert event["key"] == "incoming/x.json"
    assert event["size"] == 123
