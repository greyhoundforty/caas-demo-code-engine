from pathlib import Path

import pytest

from job.main import build_event

SAMPLES = Path(__file__).parents[2] / "samples"


def event_for(name: str) -> dict:
    # demo.sh substitutes __COMMIT__ before uploading; do the same here.
    raw = (SAMPLES / f"{name}.json").read_text().replace("__COMMIT__", "abc1234")
    return build_event("evt", f"incoming/{name}.json", raw.encode(), len(raw))


def test_good_sample_is_a_passed_build():
    event = event_for("good")
    assert (event["kind"], event["status"]) == ("build", "passed")
    assert event["commit"] == "abc1234"


def test_failed_sample_is_a_failed_build():
    event = event_for("failed")
    assert (event["kind"], event["status"]) == ("build", "failed")
    assert event["tests"]["failed"] == 3


def test_malformed_sample_is_rejected():
    event = event_for("malformed")
    assert event["kind"] == "rejected"
    assert "invalid JSON" in event["reason"]


@pytest.mark.parametrize("name", ["good", "failed", "malformed"])
def test_every_sample_contains_the_commit_placeholder(name):
    assert "__COMMIT__" in (SAMPLES / f"{name}.json").read_text()
