"""Phase 3.5.8: Validate extracted entities and relationship triples
against ontology/schema.py.

This is where the ontology "pays for itself": a future LLM extraction
step (3.5.6/3.5.7) can propose entities and triples freely from a device
document chunk, but nothing is accepted as a fact unless it validates
here. A triple whose relation isn't defined for its subject's entity
type, or whose object isn't the expected type, is rejected outright - not
guessed at, not silently coerced into something plausible-looking. This
mirrors (and is stricter than) the row-anchored table-cell guardrail in
services/document_diff_planner.py: that check can only verify a cell
value that the LLM already produced; this one refuses to let an invalid
fact be extracted as a triple in the first place.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import ENTITY_TYPES, allowed_relations


@dataclass(frozen=True)
class Entity:
    type: str
    value: str


@dataclass(frozen=True)
class Triple:
    subject: Entity
    relation: str
    obj: Entity


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str | None = None


def validate_entity(entity: Entity) -> ValidationResult:
    if entity.type not in ENTITY_TYPES:
        return ValidationResult(False, f"Unknown entity type: {entity.type!r}")
    if not entity.value or not entity.value.strip():
        return ValidationResult(False, "Entity value is empty")
    return ValidationResult(True)


def validate_triple(triple: Triple) -> ValidationResult:
    subject_result = validate_entity(triple.subject)
    if not subject_result.valid:
        return subject_result

    object_result = validate_entity(triple.obj)
    if not object_result.valid:
        return object_result

    relations = allowed_relations(triple.subject.type)
    if triple.relation not in relations:
        return ValidationResult(
            False,
            f"Relation {triple.relation!r} is not defined for subject type "
            f"{triple.subject.type!r} in the ontology",
        )

    expected_object_type = relations[triple.relation]
    if triple.obj.type != expected_object_type:
        return ValidationResult(
            False,
            f"Relation {triple.relation!r} expects object type "
            f"{expected_object_type!r}, got {triple.obj.type!r}",
        )

    return ValidationResult(True)
