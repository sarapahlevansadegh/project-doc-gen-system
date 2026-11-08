"""Rule-based table/line extraction (no LLM, no database).

The sample text below is copied from real chunks of the VL8 input documents
(document_chunks.chunk_text), including the header-less continuation chunks.
"""
from __future__ import annotations

from pathlib import Path

from ontology.table_extractor import extract_rule_based_entities
from services.conflict_benchmark import (
    EXTRACTED_NOT_FLAGGED,
    ExtractedEntity,
    load_known_conflicts,
    score,
)

FIXTURES = Path(__file__).parent / "fixtures"

DRIVER_PARAMS = """
Table 1- Functional Specifications of the Device

| No. | Parameter Name (Unit) | Range | Steps | Acceptable Tolerance | Default |
| --- | --- | --- | --- | --- | --- |
| 1 | Wavelength (nm) | 808, 1064, 650 | - | ±10nm | - |
| 3 | Emission Mode | Continuous, Pulsed | - | - | Continuous |
| 4 | Frequency (Hz) | 1-1K | 1 for 1-10 Hz 5 for 10-100 Hz 50 for 100-1000 Hz | ±20% | 10 Hz |
| 5 | Peak Power (W) | 0-8W for  808  nm (single) 0.2W for 650nm | ±100mW for 808 & 1064 | ±20% | 0.5W |
| 6 | Area () | 1-100 cm2 | 1() | - | 5 cm |
| 7 | Dose (J/) | 1-255 | 1(J/) | - | - |
| 8 | Duty Cycle (%) | 1-95 | 1% | ±20% | 50% |
"""

DRIVER_ALARMS_FIRST = """
| No. | Priority | Alarm/Warning Condition | Limit | Indicator Light | Indicator Sound | Required Action |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | High | Output running. | Tapping the Start Button | Color: Red Flashing Frequency(Hz): 1.4-2.8 | Requirements shall be checked | Laser Emission. |
| 2 | High | Laser module over temperature. | 45º | Color: Red Flashing Frequency(Hz): 1.4-2.8 | Requirements shall be checked | Immediate Laser Emission Interruption. |
"""

# continuation chunk: same table, header row missing
DRIVER_ALARMS_NEXT = """ (part 3)

| 8 | Low | The footswitch is not connected. | Detecting Voltage Change | Constant Yellow | Requirements shall be checked | No Laser Emission. |
| 12 | Low | Low Battery. | 15% of the maximum capacity |  |  | - |
"""

GUI_ALARMS = """
| No. | Priority | Alarm/Warning Condition | Text to be shown | Indicator Light | Indicator Sound | Required Action |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | High | Laser module over temperature (35º). | Over temperature. | Color: Red | Yes | Immediate Laser Emission Interruption. |
| 6 | Medium | The Handswitch is not connected. | The Handswitch is not connected. | Color: Yellow | Yes | No Laser Emission. |
| 11 | Low | The battery charge drops below 20%. | Low Battery | Color: designers choice |  | - |
"""

GUI_TEXT = """
Therapy Modes: The device shall offer multiple therapy modes. Five modes shall be available for selection, which are:
Duty Cycle: it should be possible to adjust it from 5% to 100% in 5% increments, defining the proportion of time.
Frequency: It should be possible to select the Frequency from 1 Hz to 1 KHz with the step of 1 for 1-10 Hz.
Area: Ranges from 1 cm2 to 225 cm2; by increasing the area of the treatment, the treatment time will be increased.
Dose: It ranges from 1 j/cm2 to 100j/cm2; by increasing the Dose, the treatment time will be increased.
Note: this line must be ignored.
"""

CONCEPT_TEXT = """
- Laser Wavelengths specifications: 808nm with Peak Power Up to 8 watts, 1064nm with Peak Power Up to 8 watts and a guidlight of 650 nm with the power of< 50 mW
- Frequency: 1Hz to 100KHz
"""


def _values(text, header=None):
    entities, carried = extract_rule_based_entities(text, header)
    return [e.value for e in entities], carried


def test_parameter_rows_become_one_specification_each_with_a_unique_key():
    values, _ = _values(DRIVER_PARAMS)
    assert "Duty Cycle (%) Range: 1-95" in values
    assert "Area () Range: 1-100 cm2" in values
    assert "Dose (J/) Range: 1-255" in values
    assert "Wavelength (nm) Acceptable Tolerance: ±10nm" in values
    # the three tolerances no longer share one key
    assert "Frequency (Hz) Acceptable Tolerance: ±20%" in values
    assert "Peak Power (W) Acceptable Tolerance: ±20%" in values
    # empty cells ("-") produce nothing
    assert not any(v.endswith(": -") for v in values)


def test_alarm_rows_keep_the_condition_as_key_and_the_limit_in_the_value():
    values, _ = _values(DRIVER_ALARMS_FIRST)
    temp = next(v for v in values if v.startswith("Laser module over temperature"))
    assert temp.split(":", 1)[0] == "Laser module over temperature"
    assert "limit 45º" in temp


def test_header_is_carried_into_a_headerless_continuation_chunk():
    _, carried = _values(DRIVER_ALARMS_FIRST)
    values, _ = _values(DRIVER_ALARMS_NEXT, carried)
    assert any(v.startswith("The footswitch is not connected") for v in values)
    battery = next(v for v in values if v.startswith("Low Battery"))
    assert "limit 15% of the maximum capacity" in battery


def test_headerless_table_without_a_carried_header_yields_nothing():
    values, _ = _values(DRIVER_ALARMS_NEXT, None)
    assert values == []


def test_carried_header_with_a_different_column_count_is_not_used():
    values, _ = _values("| 1 | a | b |", ["No.", "Parameter"])
    assert values == []


def test_gui_alarm_table_has_no_limit_column_so_the_number_stays_in_the_condition():
    values, _ = _values(GUI_ALARMS)
    assert any(v.startswith("Laser module over temperature (35º)") for v in values)
    assert any(v.startswith("The battery charge drops below 20%") for v in values)


def test_plain_name_value_lines_and_bullets():
    values, _ = _values(GUI_TEXT + CONCEPT_TEXT)
    assert any(v.startswith("Therapy Modes:") and "Five modes" in v for v in values)
    assert "Frequency: 1Hz to 100KHz" in values
    assert not any(v.startswith("Note:") for v in values)


def test_title_row_above_the_real_header_row():
    text = (
        "| Game’s Parameters |\n| --- |\n"
        "| No. | Parameter | Range | Step |\n"
        "| 1 | Threshold | 0-2000uv | 1uv |\n"
    )
    values, _ = _values(text)
    assert "Threshold Range: 0-2000uv" in values
    assert "Threshold Step: 1uv" in values


def test_unrecognised_table_yields_nothing():
    text = "| No. | Title | Reference File |\n| --- | --- | --- |\n| 1 | Schematic Drawing Standard | Document Code: 4714 |\n"
    assert _values(text)[0] == []


def test_long_value_is_cut_to_the_column_size():
    text = "| No. | Parameter | Range |\n| --- | --- | --- |\n| 1 | Big | " + "x" * 800 + " |\n"
    assert all(len(v) <= 500 for v in _values(text)[0])


def test_empty_text():
    assert extract_rule_based_entities("", None) == ([], None)


def test_vl8_conflicts_are_all_extracted_from_the_sample_chunks():
    """The benchmark's first-stage goal on text copied from the real chunks:
    every known VL8 conflict has both sides extracted as Specification."""
    by_type = {
        "driver_input": DRIVER_PARAMS + DRIVER_ALARMS_FIRST,
        "gui_input": GUI_ALARMS + GUI_TEXT,
        "concept": CONCEPT_TEXT,
    }
    entities = []
    for input_type, text in by_type.items():
        found, carried = extract_rule_based_entities(text, None)
        entities += [ExtractedEntity("Specification", e.value, input_type) for e in found]
        if input_type == "driver_input":
            more, _ = extract_rule_based_entities(DRIVER_ALARMS_NEXT, carried)
            entities += [ExtractedEntity("Specification", e.value, input_type) for e in more]

    report = score(load_known_conflicts(FIXTURES / "vl8_known_conflicts.json"), entities, [])
    not_extracted = [r.conflict_id for r in report.results if r.status != EXTRACTED_NOT_FLAGGED]
    assert not_extracted == []


def test_760a_conflicts_are_all_extracted_from_sample_text():
    gui = """
| No. | Parameter | Range | Step |
| --- | --- | --- | --- |
| 1 | Work Time | 1-20s | 1s |
| 4 | Release EMG Threshold | 0-10uv | 0.1uv |
| 3 | EMG Threshold | 0-2000uv | 1uv |

| No. | Parameter/Setting | Default Value/Setting |
| --- | --- | --- |
| 10 | Filter | Width |
"""
    concept = """
- Work / Rest periods: 2-99 seconds
- Release Threshold: 1-10\u03bcv(0.1 \u03bcv)
- a. Wide: 18 Hz +/- 4 Hz to 370 Hz +/- 10%
"""
    hardware = "- Threshold: 3\u03bcv-2000\u03bcv\n"
    entities = []
    for input_type, text in (("gui_input", gui), ("concept", concept), ("hardware_design", hardware)):
        found, _ = extract_rule_based_entities(text, None)
        entities += [ExtractedEntity("Specification", e.value, input_type) for e in found]

    report = score(load_known_conflicts(FIXTURES / "760a_known_conflicts.json"), entities, [])
    assert [r.conflict_id for r in report.results if r.status != EXTRACTED_NOT_FLAGGED] == []


def test_section_title_tables_keep_the_section_in_the_label():
    text = (
        "| Operating conditions |  |\n| --- | --- |\n"
        "| Ambient temperature | 10°C to +35 °C |\n"
        "| Relative humidity | 5 % to 85 % |\n"
        "|  |  |\n"
        "| Transport and storage conditions | Transport and storage conditions |\n"
        "| Ambient temperature | -10 °C to +50 °C |\n"
    )
    values, _ = _values(text)
    assert "Operating conditions Ambient temperature: 10°C to +35 °C" in values
    assert "Transport and storage conditions Ambient temperature: -10 °C to +50 °C" in values


def test_document_header_tables_are_not_read_as_sections():
    text = "| 15803 | Document Code |\n| --- | --- |\n| 00 | Revision |\n"
    assert _values(text)[0] == []


def test_two_facts_on_one_line_are_split():
    line = ("Duty Cycle: it should be possible to adjust it from 5% to 100% in 5% increments. "
            "Frequency: It should be possible to select the Frequency from 1 Hz to 1 KHz.")
    values, _ = _values(line)
    assert values == [
        "Duty Cycle: it should be possible to adjust it from 5% to 100% in 5% increments.",
        "Frequency: It should be possible to select the Frequency from 1 Hz to 1 KHz.",
    ]
