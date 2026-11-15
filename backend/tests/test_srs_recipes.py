from schemas.device import DeviceInputType
from services.srs_recipes import (
    FIXED_TEXT,
    GENERATE,
    SRS_RECIPES,
    recipes_for_device,
)

_TYPES = {t.value for t in DeviceInputType}


def test_ids_are_unique_and_input_types_are_valid():
    ids = [r.id for r in SRS_RECIPES]
    assert len(ids) == len(set(ids))
    for r in SRS_RECIPES:
        assert set(r.input_types) <= _TYPES, r.id
        if r.only_if_input:
            assert r.only_if_input in _TYPES


def test_modes_are_consistent():
    for r in SRS_RECIPES:
        assert r.mode in (GENERATE, FIXED_TEXT)
        if r.mode == FIXED_TEXT:
            assert r.fixed_text and not r.input_types
        else:
            assert r.input_types and r.fixed_text is None


def test_driver_section_only_with_driver_input():
    gui_only = {"concept", "gui_input", "hardware_design"}
    assert "3A" not in [r.id for r in recipes_for_device(gui_only)]
    assert "3A" in [r.id for r in recipes_for_device(gui_only | {"driver_input"})]


def test_optional_section_needs_explicit_request():
    types = set(_TYPES)
    assert "16" not in [r.id for r in recipes_for_device(types)]
    assert "16" in [r.id for r in recipes_for_device(types, include_optional=True)]


def test_document_order_is_kept():
    ids = [r.id for r in recipes_for_device(set(_TYPES))]
    assert ids[:4] == ["1", "2", "3A", "3B"] and ids[-1] == "15"
