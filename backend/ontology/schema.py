"""Phase 3.5.1-3.5.5: Ontology schema for the medical-device documentation
domain.

This module is pure data + validation logic - no LLM calls, no database,
no graph library. It defines a small, CLOSED set of entity types and the
relationships allowed between them. Later phases (3.5.6+, not built yet)
will extract entities/relationships from device-document chunks via an
LLM and check the result against this schema before anything is trusted
enough to enter a knowledge graph.

Kept intentionally small and grounded in the two real documents already
in this project (reference template + Input-GUI_VL8.docx), not a
general-purpose ontology: Device/Specification/Wavelength/Power/Component
cover the hardware-spec content: Alarm/Indicator cover the "Errors and
Warnings" table specifically, since that's the exact case where free-text
generation hallucinated a value today (see
services/document_diff_planner.py's table-hallucination guardrail) - an
ontology-validated triple for "which indicator light goes with which
alarm" can't be silently invented the way a table cell was, because
there's no dependent output to write, unless a matching Alarm/Indicator
triple were actually extracted and validated.
"""
from __future__ import annotations

ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "Device",
        "Specification",
        "Wavelength",
        "Power",
        "Component",
        "Alarm",
        "Indicator",
    }
)

# ONTOLOGY[subject_type][relation] = required object_type.
# A relation not listed here for a given subject type is not permitted -
# see ontology/validator.py.
ONTOLOGY: dict[str, dict[str, str]] = {
    "Device": {
        "hasSpecification": "Specification",
        "hasWavelength": "Wavelength",
        "hasPower": "Power",
        "hasComponent": "Component",
        "hasAlarm": "Alarm",
    },
    "Alarm": {
        "hasIndicator": "Indicator",
    },
}


def allowed_relations(subject_type: str) -> dict[str, str]:
    """Relations permitted FROM a given entity type, mapped to the object
    type each one must point to. Empty dict for an unknown or leaf entity
    type (e.g. "Wavelength" has no outgoing relations defined yet)."""
    return ONTOLOGY.get(subject_type, {})
