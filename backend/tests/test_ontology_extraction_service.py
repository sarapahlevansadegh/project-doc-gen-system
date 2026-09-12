"""Integration tests for services/ontology_extraction_service.py (Phase 3.5.9)
- the piece that actually connects ontology/extractor.py to the rest of the
project (persisting its output, scoped by device so cross-document
consistency checks are possible).

Plain async tests against a real Postgres connection (skipped if
unavailable), same pattern as tests/test_chunk_service.py: no manual
asyncio.new_event_loop(), relies on pytest-asyncio's session-scoped loop.
"""
from __future__ import annotations

import json
import uuid

import pytest


class _FakeLLM:
    """Returns a fixed entity-extraction response for prompts that look
    like the entity prompt, and a fixed relationship-extraction response
    for prompts that look like the relationship prompt (identified by the
    "ENTITIES:" section extract_relationships's prompt template always
    includes - see ontology/extractor.py's _RELATIONSHIP_PROMPT_TEMPLATE).
    """

    def __init__(self, entities_response: str, relationships_response: str = "[]"):
        self._entities_response = entities_response
        self._relationships_response = relationships_response
        self.prompts: list[str] = []

    def generate(self, prompt: str, max_tokens: int = 800, temperature: float = 0.1) -> str:
        self.prompts.append(prompt)
        if "ENTITIES:" in prompt:
            return self._relationships_response
        return self._entities_response


async def _db_available() -> bool:
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_extracts_and_persists_entities_and_relationships():
    if not await _db_available():
        pytest.skip("Postgres unavailable")

    from core.database import AsyncSessionLocal
    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.document_chunk import DocumentChunk
    from models.ontology import OntologyEntity, OntologyRelationship
    from services.ontology_extraction_service import extract_and_store_ontology
    from sqlalchemy import delete, select

    device_id = uuid.uuid4()
    document_id = uuid.uuid4()

    entities_response = json.dumps(
        [
            {"type": "Device", "value": "VL8"},
            {"type": "Wavelength", "value": "1064 nm"},
        ]
    )
    relationships_response = json.dumps(
        [
            {
                "subject": {"type": "Device", "value": "VL8"},
                "relation": "hasWavelength",
                "object": {"type": "Wavelength", "value": "1064 nm"},
            }
        ]
    )
    llm = _FakeLLM(entities_response, relationships_response)

    try:
        async with AsyncSessionLocal() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-ONTO-1"))
            db.add(
                DeviceDocument(
                    id=document_id,
                    device_id=device_id,
                    filename="test.docx",
                    storage_path="/tmp/test.docx",
                    file_size=123,
                    content_type=(
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                )
            )
            section_id = uuid.uuid4()
            db.add(
                DeviceDocumentSection(
                    id=section_id,
                    document_id=document_id,
                    section_name="Test Section",
                    section_type="text",
                    heading_level=1,
                    section_order=1,
                    content="VL8 operates at 1064 nm.",
                )
            )
            db.add(
                DocumentChunk(
                    device_document_id=document_id,
                    section_id=section_id,
                    chunk_text="VL8 operates at 1064 nm.",
                    chunk_index=0,
                )
            )
            await db.commit()

            result = await extract_and_store_ontology(db, document_id, llm=llm)

            assert result.device_id == device_id
            assert result.chunks_processed == 1
            assert result.entities_upserted == 2
            assert result.relationships_upserted == 1

            entities = (
                await db.execute(
                    select(OntologyEntity).where(OntologyEntity.device_id == device_id)
                )
            ).scalars().all()
            assert {(e.entity_type, e.value) for e in entities} == {
                ("Device", "VL8"),
                ("Wavelength", "1064 nm"),
            }

            relationships = (
                await db.execute(
                    select(OntologyRelationship).where(
                        OntologyRelationship.device_id == device_id
                    )
                )
            ).scalars().all()
            assert len(relationships) == 1
            assert relationships[0].relation == "hasWavelength"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(OntologyRelationship).where(OntologyRelationship.device_id == device_id)
            )
            await db.execute(
                delete(OntologyEntity).where(OntologyEntity.device_id == device_id)
            )
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.device_document_id == document_id)
            )
            await db.execute(delete(DeviceDocument).where(DeviceDocument.id == document_id))
            await db.execute(delete(Device).where(Device.id == device_id))
            await db.commit()


async def test_entity_deduplicates_across_documents_for_the_same_device():
    """The whole reason this graph is device-scoped, not document-scoped:
    the same fact extracted from two different documents belonging to the
    same device must resolve to one row, not two - otherwise a later
    consistency check has no single place to compare "what does this
    device's GUI version say" against.
    """
    if not await _db_available():
        pytest.skip("Postgres unavailable")

    from core.database import AsyncSessionLocal
    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.document_chunk import DocumentChunk
    from models.ontology import OntologyEntity
    from services.ontology_extraction_service import extract_and_store_ontology
    from sqlalchemy import delete, select

    device_id = uuid.uuid4()
    document_a_id = uuid.uuid4()
    document_b_id = uuid.uuid4()

    llm = _FakeLLM(json.dumps([{"type": "Device", "value": "VL8"}]))

    try:
        async with AsyncSessionLocal() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-ONTO-2"))
            for doc_id in (document_a_id, document_b_id):
                db.add(
                    DeviceDocument(
                        id=doc_id,
                        device_id=device_id,
                        filename="test.docx",
                        storage_path="/tmp/test.docx",
                        file_size=123,
                        content_type=(
                            "application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document"
                        ),
                    )
                )
                section_id = uuid.uuid4()
                db.add(
                    DeviceDocumentSection(
                        id=section_id,
                        document_id=doc_id,
                        section_name="Test Section",
                        section_type="text",
                        heading_level=1,
                        section_order=1,
                        content="VL8 is a high power laser.",
                    )
                )
                db.add(
                    DocumentChunk(
                        device_document_id=doc_id,
                        section_id=section_id,
                        chunk_text="VL8 is a high power laser.",
                        chunk_index=0,
                    )
                )
            await db.commit()

            await extract_and_store_ontology(db, document_a_id, llm=llm)
            await extract_and_store_ontology(db, document_b_id, llm=llm)

            entities = (
                await db.execute(
                    select(OntologyEntity).where(
                        OntologyEntity.device_id == device_id,
                        OntologyEntity.entity_type == "Device",
                        OntologyEntity.value == "VL8",
                    )
                )
            ).scalars().all()
            assert len(entities) == 1
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(OntologyEntity).where(OntologyEntity.device_id == device_id)
            )
            await db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.device_document_id.in_([document_a_id, document_b_id])
                )
            )
            await db.execute(
                delete(DeviceDocument).where(
                    DeviceDocument.id.in_([document_a_id, document_b_id])
                )
            )
            await db.execute(delete(Device).where(Device.id == device_id))
            await db.commit()
