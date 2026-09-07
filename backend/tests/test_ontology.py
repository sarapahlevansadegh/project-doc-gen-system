"""Tests for ontology/schema.py and ontology/validator.py (Phase 3.5.1-3.5.5).

Pure logic, no DB/LLM - these should be fast and dependency-free.
"""
from __future__ import annotations

from ontology.schema import ENTITY_TYPES, allowed_relations
from ontology.validator import Entity, Triple, validate_entity, validate_triple


def test_known_entity_types_are_valid():
    for entity_type in ENTITY_TYPES:
        result = validate_entity(Entity(type=entity_type, value="x"))
        assert result.valid, result.reason


def test_unknown_entity_type_is_rejected():
    result = validate_entity(Entity(type="Color", value="Blue"))
    assert result.valid is False
    assert "Unknown entity type" in result.reason


def test_empty_entity_value_is_rejected():
    result = validate_entity(Entity(type="Device", value="   "))
    assert result.valid is False
    assert "empty" in result.reason.lower()


def test_hasWavelength_triple_is_accepted():
    """The ontology's own worked example: VL8 --hasWavelength--> 810 nm."""
    triple = Triple(
        subject=Entity(type="Device", value="VL8"),
        relation="hasWavelength",
        obj=Entity(type="Wavelength", value="810 nm"),
    )
    result = validate_triple(triple)
    assert result.valid is True


def test_hasColor_triple_is_rejected():
    """The ontology's own worked example of what should be rejected:
    VL8 --hasColor--> Blue. Rejected here because "Color" isn't even a
    defined entity type (validate_entity catches it before the relation
    is checked) - the relation-not-defined path specifically is covered
    by test_relation_not_defined_for_subject_type_is_rejected below."""
    triple = Triple(
        subject=Entity(type="Device", value="VL8"),
        relation="hasColor",
        obj=Entity(type="Color", value="Blue"),
    )
    result = validate_triple(triple)
    assert result.valid is False
    assert "Unknown entity type" in result.reason


def test_triple_with_wrong_object_type_is_rejected():
    """The relation exists for this subject type, but the object doesn't
    match what the ontology says that relation must point to."""
    triple = Triple(
        subject=Entity(type="Device", value="VL8"),
        relation="hasWavelength",
        obj=Entity(type="Power", value="5 W"),  # wrong type for this relation
    )
    result = validate_triple(triple)
    assert result.valid is False
    assert "expects object type" in result.reason


def test_alarm_has_indicator_triple_is_accepted():
    """Grounded in the real hallucination bug from today: an
    Alarm-to-Indicator relationship, the exact kind of fact the table
    guardrail had to mechanically police in free text."""
    triple = Triple(
        subject=Entity(type="Alarm", value="Laser module over temperature"),
        relation="hasIndicator",
        obj=Entity(type="Indicator", value="Color: Red"),
    )
    result = validate_triple(triple)
    assert result.valid is True


def test_relation_not_defined_for_subject_type_is_rejected():
    """hasIndicator is only defined for Alarm, not for Device."""
    triple = Triple(
        subject=Entity(type="Device", value="VL8"),
        relation="hasIndicator",
        obj=Entity(type="Indicator", value="Color: Red"),
    )
    result = validate_triple(triple)
    assert result.valid is False


def test_allowed_relations_empty_for_leaf_entity_type():
    assert allowed_relations("Wavelength") == {}


def test_invalid_subject_short_circuits_before_checking_object():
    triple = Triple(
        subject=Entity(type="NotARealType", value="x"),
        relation="hasWavelength",
        obj=Entity(type="Wavelength", value="810 nm"),
    )
    result = validate_triple(triple)
    assert result.valid is False
    assert "Unknown entity type" in result.reason
