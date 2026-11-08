"""Scoring logic for the known-conflicts benchmark (database-free)."""
from __future__ import annotations

from pathlib import Path

import re

import pytest
from services.conflict_benchmark import (
    DETECTED,
    EXTRACTED_NOT_FLAGGED,
    NOT_EXTRACTED,
    PARTIALLY_EXTRACTED,
    ExtractedEntity,
    Inconsistency,
    load_known_conflicts,
    score,
)

FIXTURE = Path(__file__).parent / "fixtures" / "vl8_known_conflicts.json"
FIXTURES = [
    FIXTURE,
    Path(__file__).parent / "fixtures" / "760a_known_conflicts.json",
]

TEMP = {
    "id": "temp",
    "title": "Over temperature",
    "key_keywords": ["temperature"],
    "sources": [
        {"input_type": "gui_input", "token_regex": r"(?<!\d)35(?!\d)"},
        {"input_type": "driver_input", "token_regex": r"(?<!\d)45(?!\d)"},
    ],
}


def _spec(value, input_type):
    return ExtractedEntity("Specification", value, input_type)


def test_fixture_loads_and_every_conflict_has_two_sources():
    conflicts = load_known_conflicts(FIXTURE)
    assert len(conflicts) >= 8
    assert len({c["id"] for c in conflicts}) == len(conflicts)
    for conflict in conflicts:
        assert len({s["input_type"] for s in conflict["sources"]}) >= 2


def test_detected_when_one_key_holds_values_from_two_sources():
    entities = [
        _spec("Laser Over Temperature: 35 degrees", "gui_input"),
        _spec("Laser Over Temperature: 45 degrees", "driver_input"),
    ]
    inc = [Inconsistency("laser over temperature", (
        "Laser Over Temperature: 35 degrees", "Laser Over Temperature: 45 degrees"))]
    report = score([TEMP], entities, inc)
    assert report.results[0].status == DETECTED
    assert report.detected == 1 and report.recall == 1.0
    assert report.unmatched_inconsistencies == []


def test_extracted_under_different_keys_is_not_flagged():
    entities = [
        _spec("Over Temperature Limit: 35 degrees", "gui_input"),
        _spec("Laser Module Temperature Cutoff: 45 degrees", "driver_input"),
    ]
    report = score([TEMP], entities, [])
    assert report.results[0].status == EXTRACTED_NOT_FLAGGED


def test_only_one_source_extracted_is_partial():
    entities = [_spec("Over Temperature: 35 degrees", "gui_input")]
    assert score([TEMP], entities, []).results[0].status == PARTIALLY_EXTRACTED


def test_nothing_extracted():
    assert score([TEMP], [], []).results[0].status == NOT_EXTRACTED


def test_value_from_wrong_input_type_does_not_count():
    # the 45 degrees value exists, but it came from the GUI input, not the driver input
    entities = [
        _spec("Over Temperature: 35 degrees", "gui_input"),
        _spec("Over Temperature: 45 degrees", "gui_input"),
    ]
    assert score([TEMP], entities, []).results[0].status == PARTIALLY_EXTRACTED


def test_non_specification_entity_does_not_count_as_flaggable():
    entities = [
        _spec("Over Temperature: 35 degrees", "gui_input"),
        ExtractedEntity("Alarm", "Over temperature 45 degrees", "driver_input"),
    ]
    # extracted, but not as a Specification, so the key-based check cannot see it
    assert score([TEMP], entities, []).results[0].status == PARTIALLY_EXTRACTED


def test_unrelated_inconsistencies_are_listed_for_review():
    inc = [Inconsistency("gui software version", ("v1", "v2"))]
    report = score([TEMP], [], inc)
    assert [i.key for i in report.unmatched_inconsistencies] == ["gui software version"]


def test_decision_is_carried_into_the_result():
    conflict = dict(TEMP, decision={"value": "45 degrees", "status": "confirmed_by_engineer"})
    assert score([conflict], [], []).results[0].decision["value"] == "45 degrees"


def test_bad_regex_fails_at_load(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"conflicts":[{"id":"x","title":"x","key_keywords":["a"],"sources":['
        '{"input_type":"a","token_regex":"("},{"input_type":"b","token_regex":"b"}]}]}'
    )
    with pytest.raises(Exception):
        load_known_conflicts(bad)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_each_source_regex_matches_its_own_quote(path):
    """Catches typos in a fixture: a source's pattern must match the very
    sentence it claims to come from."""
    for conflict in load_known_conflicts(path):
        for source in conflict["sources"]:
            assert re.search(source["token_regex"], source["quote"], flags=re.IGNORECASE), (
                f"{conflict['id']}/{source['input_type']}: pattern does not match its quote"
            )


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_every_fixture_has_two_different_input_types_per_conflict(path):
    for conflict in load_known_conflicts(path):
        assert len({s["input_type"] for s in conflict["sources"]}) >= 2, conflict["id"]
