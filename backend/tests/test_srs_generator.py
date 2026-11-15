import json

import pytest
from schemas.srs import StatementLabel
from services.srs_generator import (
    InputChunk,
    build_prompt,
    generate_section,
    generate_srs_from_chunks,
    load_decisions_file,
    parse_statements,
    summarize,
)
from services.srs_recipes import SRS_RECIPES

RECIPE = {r.id: r for r in SRS_RECIPES}


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, max_tokens=0, temperature=0.0):
        self.prompts.append(prompt)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


CHUNKS = [
    InputChunk(7, "gui_input", "Home Page", "Duty Cycle: adjustable from 5% to 100% in 5% steps."),
    InputChunk(8, "driver_input", "Table 1", "Frequency (Hz) Range: 1-1K"),
    InputChunk(9, "concept", None, "Laser Class: IV Class"),
]


def _json(*items):
    return json.dumps(list(items))


def test_parse_handles_fences_object_and_unknown_label():
    raw = '```json\n{"statements": [{"text": "A", "label": "weird", "chunk_ids": ["3"]}]}\n```'
    [s] = parse_statements(raw)
    assert s.label is StatementLabel.PROPOSAL and s.needs_review and s.chunk_ids == [3]


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        parse_statements("not json")


def test_prompt_contains_chunks_and_decisions():
    p = build_prompt(RECIPE["3B"], CHUNKS[:1], {"duty_cycle_range": "5 to 100 percent"})
    assert "[C7] (gui_input / Home Page)" in p and "duty_cycle_range: 5 to 100 percent" in p


def test_fixed_text_section_does_not_call_the_model():
    llm = FakeLLM("[]")
    d = generate_section(RECIPE["14"], CHUNKS, {}, llm)
    assert d.statements[0].text == "No specific requirement is needed." and not llm.prompts


def test_section_without_matching_input_needs_input():
    d = generate_section(RECIPE["3A"], [CHUNKS[0]], {}, FakeLLM("[]"))   # no driver input
    assert d.status == "needs_input" and d.statements[0].needs_review


def test_supported_and_unsupported_statements():
    reply = _json(
        {"text": "Duty cycle shall be 5% to 100%.", "label": "input", "chunk_ids": [7]},
        {"text": "Duty cycle shall be 10% to 90%.", "label": "input", "chunk_ids": [7]},
    )
    d = generate_section(RECIPE["3B"], CHUNKS, {}, FakeLLM(reply))
    assert [s.needs_review for s in d.statements] == [False, True]
    assert d.statements[1].label is StatementLabel.PROPOSAL


def test_bad_json_is_retried_once_then_marked_needs_input():
    good = _json({"text": "Class IV laser.", "label": "input", "chunk_ids": [9]})
    d = generate_section(RECIPE["1"], CHUNKS, {}, FakeLLM("oops", good))
    assert d.status == "generated"
    d2 = generate_section(RECIPE["1"], CHUNKS, {}, FakeLLM("oops"))
    assert d2.status == "needs_input"


def test_empty_reply_means_needs_input():
    assert generate_section(RECIPE["1"], CHUNKS, {}, FakeLLM("[]")).status == "needs_input"


def test_truncation_is_flagged_not_silent():
    big = [InputChunk(i, "gui_input", None, "x" * 60) for i in range(1, 6)]
    reply = _json({"text": "Something.", "label": "proposal"})
    d = generate_section(RECIPE["3B"], big, {}, FakeLLM(reply), max_chars=130)
    assert any(s.review_reason == "input truncated" for s in d.statements)


def test_decision_overrides_are_validated():
    reply = _json({"text": "Duty cycle shall be 5 to 100 percent.", "label": "decision",
                   "decision_key": "duty_cycle_range"})
    d = generate_section(RECIPE["4"], CHUNKS, {"duty_cycle_range": "5 to 100 percent"},
                         FakeLLM(reply))
    assert d.statements[0].label is StatementLabel.DECISION and not d.statements[0].needs_review


def test_generate_srs_skips_driver_section_without_driver_input_and_summarizes():
    gui_only = [c for c in CHUNKS if c.input_type != "driver_input"]
    reply = _json({"text": "Class IV laser.", "label": "input", "chunk_ids": [9]})
    drafts = generate_srs_from_chunks(gui_only, FakeLLM(reply))
    assert "3A" not in [d.section_id for d in drafts]
    s = summarize(drafts)
    assert s["sections"] == len(drafts) and s["statements"] > 0
    assert set(s) == {"sections", "sections_needing_input", "statements",
                      "by_label", "needs_review"}


def test_load_decisions_file(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"decisions": {"a": 1, "b": "two"}}), encoding="utf-8")
    assert load_decisions_file(p) == {"a": "1", "b": "two"}
