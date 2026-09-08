"""Phase 3.5.6/3.5.7: extract entities, then relationships between them,
from device-document chunk text via LLM.

Every extracted entity is checked against ontology/validator.py before
being returned - an entity type the LLM invents that isn't in
ontology/schema.py's ENTITY_TYPES is silently dropped, not passed
through. This is the same principle as
services/document_diff_planner.py's table guardrail (don't trust free
LLM output unchecked), applied one step earlier: at extraction time
rather than after a document has already been generated from it.

extract_relationships() (3.5.7) applies the same principle one step
further: it only ever proposes a triple between two entities that were
already extracted and validated in 3.5.6 (passed in via `entities`) -
the LLM is not free to invent a new entity mid-relationship - and every
candidate triple is still checked against validate_triple() before
being returned.
"""
from __future__ import annotations

import json
import logging

from agent.llm import LLMClient
from ontology.schema import ENTITY_TYPES
from ontology.validator import Entity, Triple, validate_entity, validate_triple

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """You are extracting structured entities from a medical device technical document. Only extract entities whose type is exactly one of: {entity_types}.

TEXT:
---
{chunk_text}
---

For each entity you find, output its type (must be exactly one of the allowed types above) and its value exactly as it appears in the text. Do not invent an entity that isn't explicitly stated in the text - if the text doesn't mention something, don't extract it.

Respond with ONLY a JSON array, no markdown code fences, no commentary before or after:
[{{"type": "Device", "value": "VL8"}}, {{"type": "Wavelength", "value": "810 nm"}}]

If no entities of the allowed types are present in the text, respond with an empty array: []"""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def extract_entities(chunk_text: str, llm: LLMClient) -> list[Entity]:
    """Extract entities from one chunk of device-document text.

    Fail-soft throughout: a malformed LLM response, a non-list response,
    or an individual entity that doesn't validate against the ontology
    all result in that entity (or the whole batch, for a parse failure)
    being dropped rather than raising - a missed entity is recoverable
    later; a bad one silently entering the graph in a future phase is
    not.
    """
    if not chunk_text or not chunk_text.strip():
        return []

    prompt = _PROMPT_TEMPLATE.format(
        entity_types=", ".join(sorted(ENTITY_TYPES)),
        chunk_text=chunk_text,
    )
    raw = llm.generate(prompt, max_tokens=800, temperature=0.1)

    try:
        parsed = json.loads(_strip_json_fences(raw))
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse entity extraction response as JSON: %r", raw[:200])
        return []

    if not isinstance(parsed, list):
        logger.warning("Entity extraction response was not a JSON array: %r", raw[:200])
        return []

    entities: list[Entity] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        entity = Entity(type=item.get("type", ""), value=item.get("value", ""))
        result = validate_entity(entity)
        if result.valid:
            entities.append(entity)
        else:
            logger.info("Dropped invalid extracted entity %r: %s", entity, result.reason)

    return entities


_RELATIONSHIP_PROMPT_TEMPLATE = """You are extracting relationships between entities in a medical device technical document. You may ONLY use the entities listed below as the subject or object of a relationship - do not invent, rename, or reword any entity.

ENTITIES:
---
{entities_list}
---

TEXT:
---
{chunk_text}
---

For each relationship you find between two of the above entities, output the subject entity, the relation name, and the object entity, copying each entity's type and value EXACTLY as given in the entities list above. Do not extract a relationship whose subject or object is not one of the listed entities, and do not extract a relationship between an entity and itself.

Respond with ONLY a JSON array, no markdown code fences, no commentary before or after:
[{{"subject": {{"type": "Device", "value": "VL8"}}, "relation": "hasWavelength", "object": {{"type": "Wavelength", "value": "810 nm"}}}}]

If no relationships between the listed entities are present in the text, respond with an empty array: []"""


def extract_relationships(chunk_text: str, entities: list[Entity], llm: LLMClient) -> list[Triple]:
    """Extract relationship triples between already-extracted entities (3.5.6) from one chunk of device-document text.

    Only relationships between entities present in `entities` are ever considered - a candidate triple whose subject
    or object doesn't exactly match (type, value) one of the given entities is dropped, so the LLM cannot invent a
    new entity while proposing a relationship. Every remaining candidate is then checked against
    ontology/validator.py's validate_triple(), so a relation not defined for the subject's entity type, or an object
    of the wrong type, is also dropped. Fail-soft throughout, same as extract_entities: a malformed response, a
    non-list response, or an individual triple that fails either check is dropped rather than raising.
    """
    if not chunk_text or not chunk_text.strip():
        return []
    if len(entities) < 2:
        # A relationship needs two known entities to connect; skip the LLM call entirely.
        return []

    known = {(entity.type, entity.value) for entity in entities}
    entities_list = "\n".join(
        f'- {{"type": "{entity.type}", "value": "{entity.value}"}}' for entity in entities
    )

    prompt = _RELATIONSHIP_PROMPT_TEMPLATE.format(entities_list=entities_list, chunk_text=chunk_text)
    raw = llm.generate(prompt, max_tokens=800, temperature=0.1)

    try:
        parsed = json.loads(_strip_json_fences(raw))
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse relationship extraction response as JSON: %r", raw[:200])
        return []

    if not isinstance(parsed, list):
        logger.warning("Relationship extraction response was not a JSON array: %r", raw[:200])
        return []

    triples: list[Triple] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue

        subject_raw = item.get("subject")
        object_raw = item.get("object")
        if not isinstance(subject_raw, dict) or not isinstance(object_raw, dict):
            continue

        subject = Entity(type=subject_raw.get("type", ""), value=subject_raw.get("value", ""))
        obj = Entity(type=object_raw.get("type", ""), value=object_raw.get("value", ""))
        relation = item.get("relation", "")

        if (subject.type, subject.value) not in known or (obj.type, obj.value) not in known:
            logger.info(
                "Dropped triple referencing an entity outside the extracted set: %r -[%s]-> %r",
                subject, relation, obj,
            )
            continue

        triple = Triple(subject=subject, relation=relation, obj=obj)
        result = validate_triple(triple)
        if result.valid:
            triples.append(triple)
        else:
            logger.info("Dropped invalid extracted triple %r: %s", triple, result.reason)

    return triples
