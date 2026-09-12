"""Phase 3.5.9: run ontology/extractor.py over a device document's already-
generated chunks (rag/chunk_service.py) and persist the result.

This is the missing link that connects ontology/extractor.py (pure
functions, no DB, no wiring - see its own docstring) to the rest of the
project: nothing outside ontology/ and its tests referenced it before
this file existed.

Mirrors rag.chunk_service.generate_and_store_chunks / the
/devices/documents/{id}/chunks endpoint pattern: this is its own explicit,
re-triggerable step (LLM-call-heavy, one call per chunk for entities plus
one more for relationships), not something that runs automatically on
upload.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from agent.llm import LLMClient
from models.device_document import DeviceDocument
from models.document_chunk import DocumentChunk
from models.ontology import OntologyEntity, OntologyRelationship
from ontology.extractor import extract_entities, extract_relationships
from ontology.validator import Entity
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OntologyExtractionResult:
    document_id: uuid.UUID
    device_id: uuid.UUID
    chunks_processed: int
    entities_upserted: int
    relationships_upserted: int


async def _get_or_create_entity(
    db: AsyncSession, device_id: uuid.UUID, entity: Entity, source_chunk_id: int
) -> uuid.UUID:
    """Return the id of the OntologyEntity row for (device_id, entity),
    inserting it if this exact fact hasn't been seen for this device
    before (see models/ontology.py's unique constraint - this is the
    dedup point: the same fact re-extracted from a different chunk or a
    different document for the same device resolves to the same row).
    """
    stmt = (
        pg_insert(OntologyEntity)
        .values(
            id=uuid.uuid4(),
            device_id=device_id,
            entity_type=entity.type,
            value=entity.value,
            source_chunk_id=source_chunk_id,
        )
        .on_conflict_do_nothing(
            index_elements=["device_id", "entity_type", "value"]
        )
        .returning(OntologyEntity.id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is not None:
        return row[0]

    # Already existed - on_conflict_do_nothing() doesn't return the
    # conflicting row, so fetch its id explicitly.
    existing = await db.execute(
        select(OntologyEntity.id).where(
            OntologyEntity.device_id == device_id,
            OntologyEntity.entity_type == entity.type,
            OntologyEntity.value == entity.value,
        )
    )
    return existing.scalar_one()


async def extract_and_store_ontology(
    db: AsyncSession,
    document_id: uuid.UUID,
    llm: LLMClient | None = None,
) -> OntologyExtractionResult:
    """Extract entities + relationships from every chunk of `document_id`
    and persist them into the device-scoped ontology graph.

    Fail-soft per chunk, same principle as ontology/extractor.py itself:
    one chunk's extraction failing (LLM error, malformed response - already
    handled inside extract_entities/extract_relationships by returning an
    empty list) does not abort the rest of the document.
    """
    document = await db.get(DeviceDocument, document_id)
    if document is None:
        raise ValueError(f"No device document found for id={document_id}")

    llm = llm or LLMClient()

    chunks_result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.device_document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = chunks_result.scalars().all()

    entities_upserted = 0
    relationships_upserted = 0

    for chunk in chunks:
        try:
            chunk_entities = await asyncio.to_thread(
                extract_entities, chunk.chunk_text, llm
            )
        except Exception:
            logger.exception(
                "Entity extraction failed for chunk_id=%s, skipping", chunk.id
            )
            continue

        if not chunk_entities:
            continue

        entity_id_by_key: dict[tuple[str, str], uuid.UUID] = {}
        for entity in chunk_entities:
            entity_id = await _get_or_create_entity(db, document.device_id, entity, chunk.id)
            entity_id_by_key[(entity.type, entity.value)] = entity_id
            entities_upserted += 1

        try:
            triples = await asyncio.to_thread(
                extract_relationships, chunk.chunk_text, chunk_entities, llm
            )
        except Exception:
            logger.exception(
                "Relationship extraction failed for chunk_id=%s, skipping", chunk.id
            )
            continue

        for triple in triples:
            subject_id = entity_id_by_key.get((triple.subject.type, triple.subject.value))
            object_id = entity_id_by_key.get((triple.obj.type, triple.obj.value))
            if subject_id is None or object_id is None:
                # Shouldn't happen - extract_relationships only proposes
                # triples grounded in chunk_entities - but don't let a
                # lookup miss silently write a broken FK.
                continue

            stmt = (
                pg_insert(OntologyRelationship)
                .values(
                    id=uuid.uuid4(),
                    device_id=document.device_id,
                    subject_id=subject_id,
                    relation=triple.relation,
                    object_id=object_id,
                    source_chunk_id=chunk.id,
                )
                .on_conflict_do_nothing(
                    index_elements=["subject_id", "relation", "object_id"]
                )
            )
            await db.execute(stmt)
            relationships_upserted += 1

    await db.commit()

    return OntologyExtractionResult(
        document_id=document_id,
        device_id=document.device_id,
        chunks_processed=len(chunks),
        entities_upserted=entities_upserted,
        relationships_upserted=relationships_upserted,
    )
