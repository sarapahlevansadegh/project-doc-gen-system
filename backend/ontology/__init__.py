"""Phase 3.5: Ontology layer for the medical-device documentation domain.

See schema.py for the entity types/relationships and validator.py for
checking extracted entities/triples against that schema. No LLM
extraction or graph construction yet (3.5.6+) - this package is
currently pure schema + validation logic.
"""
from ontology.schema import ENTITY_TYPES, ONTOLOGY, allowed_relations
from ontology.validator import Entity, Triple, ValidationResult, validate_entity, validate_triple
from ontology.extractor import extract_entities

__all__ = [
    "ENTITY_TYPES",
    "ONTOLOGY",
    "allowed_relations",
    "Entity",
    "Triple",
    "ValidationResult",
    "validate_entity",
    "validate_triple",
    "extract_entities",
]
