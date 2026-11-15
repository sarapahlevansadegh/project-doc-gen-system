"""Section recipes for the Software Requirements (SRS) draft.

Static data, no LLM and no database. Built from the two approved SRS
documents (VL8 17187 and Biofeedback 760A 14253), which follow the same
company form (F73000RD22) and the same IEC 62304 section list.

Only sections present in both samples are required; a section found in one
sample only is optional. Sections that depend on a hardware module are
conditional: they are generated only if that input exists for the device.
Input types are the values of schemas.device.DeviceInputType.
"""
from __future__ import annotations

from dataclasses import dataclass

SRS_FORM_CODE = "F73000RD22"

GENERATE = "generate"        # written from the device inputs
FIXED_TEXT = "fixed_text"    # same words in both samples, no input needed


@dataclass(frozen=True)
class SectionRecipe:
    id: str
    title: str
    mode: str                          # GENERATE | FIXED_TEXT
    input_types: tuple[str, ...]       # inputs that feed this section
    form: str                          # "bullets" | "table" | "bullets_and_table"
    guidance: str                      # style notes taken from the samples
    required: bool = True
    only_if_input: str | None = None   # generate only if this input type exists
    fixed_text: str | None = None


_ALL = ("concept", "gui_input", "driver_input", "hardware_design")

SRS_RECIPES: tuple[SectionRecipe, ...] = (
    SectionRecipe(
        "1", "Software purposes", GENERATE, ("concept", "gui_input", "driver_input"),
        "bullets",
        "Explain what the software of this device does and how the GUI and, if present, "
        "the driver software communicate (serial protocol named in the inputs).",
    ),
    SectionRecipe(
        "2", "Physical characteristics and computing environment", GENERATE,
        ("hardware_design", "driver_input", "gui_input"), "table",
        "Table of code environment, compiler, operating system and hardware for each "
        "software piece. Leave any cell the inputs do not state as needing engineer input.",
    ),
    SectionRecipe(
        "3A", "Driver software requirements", GENERATE,
        ("driver_input", "hardware_design"), "bullets_and_table",
        "Bullets starting with 'Capability to ...'; then a table of driver functions "
        "(function description, requirement, number).",
        only_if_input="driver_input",
    ),
    SectionRecipe(
        "3B", "GUI software requirements", GENERATE, ("gui_input", "concept"),
        "bullets_and_table",
        "Bullets starting with 'Capability to ...'; then a table with columns "
        "function of software, customer needs, software requirements, number, one row per page.",
    ),
    SectionRecipe(
        "4", "Parameters", GENERATE, ("driver_input", "gui_input", "concept"), "table",
        "Three tables: ranges and limits (parameter, range, step, description), defaults "
        "(parameter, default value), and a short note on data characteristics.",
    ),
    SectionRecipe(
        "5", "Interfaces requirements", GENERATE, _ALL, "bullets",
        "Subsections: graphical user interface, hardware interfaces, communication "
        "interfaces, audible interfaces. Include units on parameter buttons.",
    ),
    SectionRecipe(
        "6", "Software-driven error messages", GENERATE, ("gui_input", "driver_input"),
        "table",
        "Table: description, error text, audible warning. If the inputs define no error "
        "messages, say so in one sentence.",
    ),
    SectionRecipe(
        "7", "Security requirements", GENERATE, ("gui_input",), "bullets",
        "Password, service page protection and reset capabilities, each with the "
        "settings path.",
    ),
    SectionRecipe(
        "8", "Usability engineering requirements", GENERATE, ("gui_input",), "bullets",
        "Help pages and their items; refer to the usability document if the inputs name one.",
    ),
    SectionRecipe(
        "9", "Requirements related to methods of operation", GENERATE, ("gui_input",),
        "bullets",
        "Help section, information per page or protocol, and how the user reaches them.",
    ),
    SectionRecipe(
        "10", "User documentation to be developed", GENERATE, ("concept", "gui_input"),
        "bullets", "Name the user manuals that are required.",
    ),
    SectionRecipe(
        "11", "Regularity requirements", GENERATE, _ALL, "bullets",
        "One bullet per applicable standard listed in the input standards tables, saying "
        "what it is needed for.",
    ),
    SectionRecipe(
        "12", "Applicable risk control measures", GENERATE, _ALL, "table",
        "One-column table of risk control measures that the inputs ask the software to "
        "provide (alarms, interlock, timers, password). Refer to the risk management file.",
    ),
    SectionRecipe(
        "13", "User maintenance requirements", GENERATE, ("concept", "hardware_design"),
        "bullets",
        "Cleaning, transport, calibration and inspection advice, only as far as the "
        "inputs or an approved rule support it.",
    ),
    SectionRecipe(
        "14", "Data definition and database requirements", FIXED_TEXT, (), "bullets",
        "Same sentence in both samples.",
        fixed_text="No specific requirement is needed.",
    ),
    SectionRecipe(
        "15", "Installation and acceptance requirements at the operation and "
        "maintenance site", FIXED_TEXT, (), "bullets",
        "Same sentence in both samples.",
        fixed_text="No specific requirement is needed.",
    ),
    SectionRecipe(
        "16", "Software system testing requirements", GENERATE, ("gui_input", "driver_input"),
        "bullets",
        "Present in the VL8 sample only (references the test procedure forms). Optional.",
        required=False,
    ),
)


def recipes_for_device(
    available_input_types: set[str], include_optional: bool = False
) -> list[SectionRecipe]:
    """Sections to generate for a device, in document order."""
    chosen = []
    for r in SRS_RECIPES:
        if not r.required and not include_optional:
            continue
        if r.only_if_input and r.only_if_input not in available_input_types:
            continue
        chosen.append(r)
    return chosen
