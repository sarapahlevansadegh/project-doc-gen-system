"""Tests for ontology/extractor.py (Phase 3.5.6).

Fake LLMClient (generate_fn-style, same pattern as tests/test_journey.py
and tests/test_document_diff_planner.py) - no real model call.
"""
from __future__ import annotations

import json

from ontology.extractor import extract_entities


class _FakeLLM:
    def __init__(self, response: str):
        self._response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str, max_tokens: int = 800, temperature: float = 0.1) -> str:
        self.prompts.append(prompt)
        return self._response


def test_extracts_valid_entities():
    response = json.dumps(
        [
            {"type": "Device", "value": "VL8"},
            {"type": "Wavelength", "value": "810 nm"},
            {"type": "Power", "value": "5 W"},
        ]
    )
    llm = _FakeLLM(response)

    entities = extract_entities("VL8 operates at 810 nm with a maximum power of 5 W.", llm)

    assert len(entities) == 3
    assert entities[0].type == "Device" and entities[0].value == "VL8"
    assert entities[1].type == "Wavelength" and entities[1].value == "810 nm"
    assert entities[2].type == "Power" and entities[2].value == "5 W"


def test_prompt_includes_the_chunk_text_and_allowed_types():
    llm = _FakeLLM("[]")
    extract_entities("The laser diode reaches 810 nm.", llm)

    assert len(llm.prompts) == 1
    assert "The laser diode reaches 810 nm." in llm.prompts[0]
    assert "Wavelength" in llm.prompts[0]
    assert "Device" in llm.prompts[0]


def test_drops_entity_with_invalid_type():
    """The model invents an entity type that isn't in the ontology - it
    should be dropped, not passed through."""
    response = json.dumps(
        [
            {"type": "Device", "value": "VL8"},
            {"type": "Color", "value": "Blue"},  # not a real ontology type
        ]
    )
    llm = _FakeLLM(response)

    entities = extract_entities("Some text.", llm)

    assert len(entities) == 1
    assert entities[0].type == "Device"


def test_drops_entity_with_empty_value():
    response = json.dumps([{"type": "Device", "value": ""}])
    llm = _FakeLLM(response)

    entities = extract_entities("Some text.", llm)

    assert entities == []


def test_malformed_json_returns_empty_list_not_crash():
    llm = _FakeLLM("this is not json")
    entities = extract_entities("Some text.", llm)
    assert entities == []


def test_non_list_json_returns_empty_list():
    llm = _FakeLLM(json.dumps({"type": "Device", "value": "VL8"}))
    entities = extract_entities("Some text.", llm)
    assert entities == []


def test_response_wrapped_in_code_fences_is_still_parsed():
    response = "```json\n" + json.dumps([{"type": "Device", "value": "VL8"}]) + "\n```"
    llm = _FakeLLM(response)

    entities = extract_entities("Some text.", llm)

    assert len(entities) == 1
    assert entities[0].value == "VL8"


def test_empty_chunk_text_skips_llm_call():
    llm = _FakeLLM("[]")
    entities = extract_entities("   ", llm)
    assert entities == []
    assert llm.prompts == []


def test_non_dict_items_in_response_are_skipped():
    llm = _FakeLLM(json.dumps(["not a dict", {"type": "Device", "value": "VL8"}]))
    entities = extract_entities("Some text.", llm)
    assert len(entities) == 1
    assert entities[0].value == "VL8"
