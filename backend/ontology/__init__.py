"""Phase 3.5: Ontology layer for the medical-device documentation domain.

See schema.py for the entity types/relationships and validator.py for
checking extracted entities/triples against that schema. extractor.py
(3.5.6/3.5.7) does the LLM extraction of entities and, from those
entities, relationship triples; no graph construction yet.
"""
from ontology.schema import ENTITY_TYPES, ONTOLOGY, allowed_relations
from ontology.validator import Entity, Triple, ValidationResult, validate_entity, validate_triple
from ontology.extractor import extract_entities, extract_relationships

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
    "extract_relationships",
]
