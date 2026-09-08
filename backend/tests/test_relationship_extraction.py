"""Tests for ontology/extractor.py's extract_relationships (Phase 3.5.7).

Fake LLMClient (generate_fn-style, same pattern as
test_entity_extraction.py) - no real model call.
"""
from __future__ import annotations

import json

from ontology.extractor import extract_relationships
from ontology.validator import Entity


class _FakeLLM:
    def __init__(self, response: str):
        self._response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str, max_tokens: int = 800, temperature: float = 0.1) -> str:
        self.prompts.append(prompt)
        return self._response


DEVICE = {"type": "Device", "value": "VL8"}
WAVELENGTH = {"type": "Wavelength", "value": "810 nm"}
ALARM = {"type": "Alarm", "value": "Over temperature"}
INDICATOR = {"type": "Indicator", "value": "Red LED"}


def test_valid_relationship_between_known_entities_is_accepted():
    """(a) A valid relationship between two already-extracted entities is accepted."""
    response = json.dumps(
        [{"subject": DEVICE, "relation": "hasWavelength", "object": WAVELENGTH}]
    )
    llm = _FakeLLM(response)
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("VL8 operates at 810 nm.", entities, llm)

    assert len(triples) == 1
    assert triples[0].subject == Entity(type="Device", value="VL8")
    assert triples[0].relation == "hasWavelength"
    assert triples[0].obj == Entity(type="Wavelength", value="810 nm")


def test_relationship_referencing_entity_outside_extracted_set_is_rejected():
    """(b) Subject/object not present in the given entities list is rejected,
    even though the triple would otherwise be valid against the ontology -
    the LLM must not invent an entity mid-relationship."""
    response = json.dumps(
        [
            {
                "subject": DEVICE,
                "relation": "hasWavelength",
                "object": {"type": "Wavelength", "value": "1064 nm"},  # not in `entities`
            }
        ]
    )
    llm = _FakeLLM(response)
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("VL8 operates at 810 nm and 1064 nm.", entities, llm)

    assert triples == []


def test_relationship_not_defined_in_ontology_is_rejected():
    """(c) A relation/object-type combination not defined in the ontology is
    rejected by validate_triple(), even though both entities were extracted."""
    response = json.dumps(
        [{"subject": WAVELENGTH, "relation": "hasComponent", "object": DEVICE}]
    )
    llm = _FakeLLM(response)
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("VL8 operates at 810 nm.", entities, llm)

    assert triples == []


def test_relationship_with_wrong_object_type_is_rejected():
    """Relation is valid for the subject type, but the object's type doesn't
    match what the ontology requires."""
    response = json.dumps(
        [{"subject": DEVICE, "relation": "hasAlarm", "object": WAVELENGTH}]
    )
    llm = _FakeLLM(response)
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("Some text.", entities, llm)

    assert triples == []


def test_multi_hop_relationship_chain_is_accepted():
    """Device->Alarm->Indicator: both triples valid and both entities known."""
    response = json.dumps(
        [
            {"subject": DEVICE, "relation": "hasAlarm", "object": ALARM},
            {"subject": ALARM, "relation": "hasIndicator", "object": INDICATOR},
        ]
    )
    llm = _FakeLLM(response)
    entities = [
        Entity(type="Device", value="VL8"),
        Entity(type="Alarm", value="Over temperature"),
        Entity(type="Indicator", value="Red LED"),
    ]

    triples = extract_relationships("Over temperature triggers the red LED.", entities, llm)

    assert len(triples) == 2
    assert triples[0].relation == "hasAlarm"
    assert triples[1].relation == "hasIndicator"


def test_prompt_includes_chunk_text_and_entities_list():
    llm = _FakeLLM("[]")
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    extract_relationships("The laser diode reaches 810 nm.", entities, llm)

    assert len(llm.prompts) == 1
    assert "The laser diode reaches 810 nm." in llm.prompts[0]
    assert '"type": "Device", "value": "VL8"' in llm.prompts[0]
    assert '"type": "Wavelength", "value": "810 nm"' in llm.prompts[0]


def test_fewer_than_two_entities_skips_llm_call():
    llm = _FakeLLM("[]")
    entities = [Entity(type="Device", value="VL8")]

    triples = extract_relationships("VL8 is a laser device.", entities, llm)

    assert triples == []
    assert llm.prompts == []


def test_empty_chunk_text_skips_llm_call():
    llm = _FakeLLM("[]")
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("   ", entities, llm)

    assert triples == []
    assert llm.prompts == []


def test_malformed_json_returns_empty_list_not_crash():
    llm = _FakeLLM("this is not json")
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("Some text.", entities, llm)

    assert triples == []


def test_non_list_json_returns_empty_list():
    llm = _FakeLLM(json.dumps({"subject": DEVICE, "relation": "hasWavelength", "object": WAVELENGTH}))
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("Some text.", entities, llm)

    assert triples == []


def test_response_wrapped_in_code_fences_is_still_parsed():
    response = "```json\n" + json.dumps(
        [{"subject": DEVICE, "relation": "hasWavelength", "object": WAVELENGTH}]
    ) + "\n```"
    llm = _FakeLLM(response)
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("Some text.", entities, llm)

    assert len(triples) == 1


def test_non_dict_items_in_response_are_skipped():
    response = json.dumps(
        ["not a dict", {"subject": DEVICE, "relation": "hasWavelength", "object": WAVELENGTH}]
    )
    llm = _FakeLLM(response)
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("Some text.", entities, llm)

    assert len(triples) == 1


def test_item_missing_subject_or_object_is_skipped():
    response = json.dumps(
        [
            {"relation": "hasWavelength", "object": WAVELENGTH},  # missing subject
            {"subject": DEVICE, "relation": "hasWavelength", "object": WAVELENGTH},
        ]
    )
    llm = _FakeLLM(response)
    entities = [Entity(type="Device", value="VL8"), Entity(type="Wavelength", value="810 nm")]

    triples = extract_relationships("Some text.", entities, llm)

    assert len(triples) == 1
