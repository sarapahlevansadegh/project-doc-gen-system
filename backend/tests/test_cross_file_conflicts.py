"""Cross-file comparison (no database, no LLM).

The values below are copied from what the VL8 and 760A benchmark devices
actually hold in ontology_entities (see scripts/eval_conflicts.py output).
"""
from __future__ import annotations

from services.conflict_benchmark import DETECTED, ExtractedEntity, load_known_conflicts, score
from services.cross_file_conflicts import (
    CROSS_FILE,
    UNPAIRED_ALARM,
    WITHIN_FILE,
    SourcedValue,
    find_conflicts,
    normalize_name,
    number_signature,
)
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

GUI_TEMP = ("Laser module over temperature (35º): priority High; text to be shown Over temperature.; "
            "indicator light Color: Red; indicator sound Yes; required action Immediate Laser Emission Interruption.")
DRIVER_TEMP = ("Laser module over temperature: priority High; limit 45º; indicator light Color: Red Flashing "
               "Frequency(Hz): 1.4-2.8; indicator sound Requirements shall be checked; "
               "required action Immediate LaserEmission Interruption.")
GUI_INTERLOCK = ("The interlock is not connected: priority Medium; text to be shown The interlock is not connected.; "
                 "indicator light Color: Yellow; indicator sound Yes; required action No Laser Emission.")
DRIVER_INTERLOCK = ("The interlock is not connected: priority Low; limit Detecting Voltage Change; "
                    "indicator light ConstantYellow; required action No Laser Emission.")
GUI_PASSWORD = ("The entered password is wrong: priority Low; text to be shown The entered password is wrong.; "
                "indicator light Color: designers choice; required action Sign-in Failure.")
DRIVER_PASSWORD = ("The entered password is wrong: priority Low; indicator light Constant Yellow; "
                   "required action Sign-in Failure.")


def _items(*pairs):
    return [SourcedValue(v, t) for t, v in pairs]


def _by_key(findings, kind):
    return {f.key: f for f in findings if f.kind == kind}


def test_names_are_normalised():
    assert normalize_name("Duty Cycle (%) Range") == normalize_name("Duty cycle") == "duty cycle"
    assert normalize_name("The interlock is not connected.") == "interlock is not connected"
    assert normalize_name("Dose (J/) Range") == "dose"
    assert normalize_name("Frequency(Hz)") == "frequency"
    assert normalize_name("Duty Cycle (%) Steps") == "duty cycle step"
    assert normalize_name("Duty Cycle (%) Acceptable Tolerance") == "duty cycle acceptable tolerance"


def test_number_signature_scales_units():
    assert number_signature("1-1K") == number_signature("1 Hz to 1 KHz") == frozenset({"1", "1000"})
    assert number_signature("0.2W for 650nm") >= frozenset({"200", "650"})
    assert number_signature("50 mW") == frozenset({"50"})
    assert number_signature("8 watts") == frozenset({"8000"})
    assert number_signature("1 j/cm2 to 100j/cm2") == frozenset({"1", "100"})
    assert number_signature("Width") == frozenset()


def test_duty_cycle_conflict_between_all_three_files():
    findings = find_conflicts(_items(
        ("concept", "Duty Cycle: 0-100 %"),
        ("concept", "Duty cycle: 0-100 %"),
        ("gui_input", "Duty Cycle: 5% to 100% in 5% increments"),
        ("driver_input", "Duty Cycle (%) Range: 1-95"),
        ("driver_input", "Duty Cycle (%) Steps: 1%"),
    ))
    cross = [f for f in findings if f.kind == CROSS_FILE and f.key == "duty cycle"]
    assert len(cross) == 3  # concept/gui, concept/driver, driver/gui
    assert not any(f.key == "duty cycle step" for f in findings)


def test_frequency_written_two_ways_is_not_a_conflict_but_100khz_is():
    findings = find_conflicts(_items(
        ("gui_input", "Frequency Range: 1 Hz to 1 KHz"),
        ("driver_input", "Frequency (Hz) Range: 1-1K"),
        ("concept", "Frequency: 1Hz to 100KHz"),
    ))
    pairs = {frozenset(t for t, _ in f.values) for f in findings if f.kind == CROSS_FILE}
    assert pairs == {frozenset({"concept", "gui_input"}), frozenset({"concept", "driver_input"})}


def test_a_contained_value_is_not_a_conflict():
    findings = find_conflicts(_items(
        ("driver_input", "Peak Power (W): 0-8W for 808 nm (single) 0-8W for 1064 nm (single) 0.2W for 650nm"),
        ("concept", "Peak Power (W): 8 watts"),
    ))
    assert [f for f in findings if f.kind == CROSS_FILE] == []


def test_same_label_twice_in_one_file_is_within_file_not_cross_file():
    findings = find_conflicts(_items(
        ("driver_input", "Ambient temperature: -10 °C to +50 °C"),
        ("driver_input", "Ambient temperature: 10°C to +35 °C"),
    ))
    assert [f.kind for f in findings] == [WITHIN_FILE]


def test_section_qualified_names_do_not_collide():
    findings = find_conflicts(_items(
        ("hardware_design", "Operating conditions Ambient temperature: 10°C to +35 °C"),
        ("hardware_design", "Transport and storage conditions Ambient temperature: -10 °C to +50 °C"),
    ))
    assert findings == []


def test_alarm_limit_number_conflict():
    findings = find_conflicts(_items(("gui_input", GUI_TEMP), ("driver_input", DRIVER_TEMP)))
    cross = _by_key(findings, CROSS_FILE)
    assert list(cross) == ["laser module over temperature"]
    assert "limit" in cross["laser module over temperature"].note


def test_alarm_priority_conflict_and_matching_alarm_is_quiet():
    findings = find_conflicts(_items(
        ("gui_input", GUI_INTERLOCK), ("driver_input", DRIVER_INTERLOCK),
        ("gui_input", GUI_PASSWORD), ("driver_input", DRIVER_PASSWORD),
    ))
    cross = _by_key(findings, CROSS_FILE)
    assert list(cross) == ["interlock is not connected"]
    assert "priority" in cross["interlock is not connected"].note


def test_alarm_only_in_one_file_is_listed_as_unpaired():
    findings = find_conflicts(_items(
        ("gui_input", "The Handswitch is not connected: priority Medium; required action No Laser Emission."),
        ("driver_input", "The footswitch is not connected: priority Low; required action No Laser Emission."),
    ))
    unpaired = {(f.key, f.values[0][0]) for f in findings if f.kind == UNPAIRED_ALARM}
    assert unpaired == {("handswitch is not connected", "gui_input"),
                        ("footswitch is not connected", "driver_input")}


def test_findings_feed_the_benchmark():
    entities = [
        ExtractedEntity("Specification", "Duty Cycle: 5% to 100% in 5% increments", "gui_input"),
        ExtractedEntity("Specification", "Duty Cycle (%) Range: 1-95", "driver_input"),
        ExtractedEntity("Specification", GUI_TEMP, "gui_input"),
        ExtractedEntity("Specification", DRIVER_TEMP, "driver_input"),
    ]
    findings = find_conflicts([SourcedValue(e.value, e.input_type) for e in entities])
    inconsistencies = [f.to_inconsistency() for f in findings if f.kind == CROSS_FILE]
    conflicts = [c for c in load_known_conflicts(FIXTURES / "vl8_known_conflicts.json")
                 if c["id"] in {"duty_cycle_range", "over_temperature_limit"}]
    report = score(conflicts, entities, inconsistencies)
    assert [r.status for r in report.results] == [DETECTED, DETECTED]
