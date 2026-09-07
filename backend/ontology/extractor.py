"""Phase 3.5.6: extract entities from device-document chunk text via LLM.

Every extracted entity is checked against ontology/validator.py before
being returned - an entity type the LLM invents that isn't in
ontology/schema.py's ENTITY_TYPES is silently dropped, not passed
through. This is the same principle as
services/document_diff_planner.py's table guardrail (don't trust free
LLM output unchecked), applied one step earlier: at extraction time
rather than after a document has already been generated from it.
"""
from __future__ import annotations

import json
import logging

from agent.llm import LLMClient
from ontology.schema import ENTITY_TYPES
from ontology.validator import Entity, validate_entity

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
