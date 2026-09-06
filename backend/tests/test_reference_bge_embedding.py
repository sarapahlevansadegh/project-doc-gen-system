"""Integration test for rag/reference_bge_embedding.find_matching_device_chunks.

Runs against a real Postgres connection (skipped if unavailable), same
pattern as tests/test_rag.py and tests/test_chunk_service.py. Since
document_templates.embedding and document_chunks.embedding are now both
bge-base-en-v1.5 (see migration 0010_consolidate_reference_embedding), this
test sets deterministic keyword-vectors directly on the rows rather than
calling the real embedding model (no torch needed) - it's testing the
cosine-search/ranking logic, not embedding quality.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

EMBED_DIM = 768
_KEYWORDS = ["sensor", "calibration", "wiring", "interface", "color", "button"]


def _keyword_vector(text: str) -> list[float]:
    lowered = text.lower()
    vec = [0.0] * EMBED_DIM
    for i, kw in enumerate(_KEYWORDS):
        if kw in lowered:
            vec[i] = 1.0
    return vec


class _FakeEmbeddingService:
    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        return [_keyword_vector(t) for t in texts]


@pytest.fixture
def _db_session():
    try:
        from core.database import AsyncSessionLocal, get_engine
    except ModuleNotFoundError:
        pytest.skip("async app stack unavailable")

    loop = asyncio.new_event_loop()
    try:
        from sqlalchemy import text

        async def _ok():
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))

        try:
            loop.run_until_complete(_ok())
        except Exception as exc:
            if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
                pytest.skip("Postgres unavailable")
            raise

        yield loop, AsyncSessionLocal
    finally:
        try:
            loop.run_until_complete(get_engine().dispose())
        except Exception:
            pass
        loop.close()


def test_find_matching_device_chunks_ranks_by_similarity(_db_session, monkeypatch):
    loop, session_factory = _db_session

    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.document_chunk import DocumentChunk
    from models.template import DocumentTemplate, ReferenceDocument
    from rag import chunk_service, reference_bge_embedding
    from sqlalchemy import delete

    fake_service = _FakeEmbeddingService()
    monkeypatch.setattr(chunk_service, "get_device_embedding_service", lambda: fake_service)
    monkeypatch.setattr(chunk_service, "bge_token_counter", lambda: (lambda t: len(t.split())))

    device_id = uuid.uuid4()
    document_id = uuid.uuid4()
    section_sensor_id = uuid.uuid4()
    section_color_id = uuid.uuid4()
    reference_id = uuid.uuid4()
    ref_section_id = uuid.uuid4()

    async def _run():
        async with session_factory() as db:
            # parents first, flushed, so children's FKs always resolve
            # regardless of unit-of-work insert ordering across mappers
            # that have no ORM relationship() between them (Device<->
            # DeviceDocument do; ReferenceDocument<->DocumentTemplate don't).
            db.add(Device(id=device_id, name="Test Device", document_code="TST-2"))
            db.add(
                DeviceDocument(
                    id=document_id,
                    device_id=device_id,
                    filename="test.docx",
                    storage_path="/tmp/test2.docx",
                    file_size=1,
                )
            )
            db.add(
                ReferenceDocument(
                    id=reference_id,
                    filename="ref.docx",
                    template_name="ref",
                    embedding_model="BAAI/bge-base-en-v1.5",
                    embedding_dimension=EMBED_DIM,
                )
            )
            await db.flush()

            # one device section clearly about sensor wiring/calibration...
            db.add(
                DeviceDocumentSection(
                    id=section_sensor_id,
                    document_id=document_id,
                    section_name="Sensor Setup",
                    section_type="text",
                    heading_level=1,
                    section_order=1,
                    content="This section covers sensor wiring and calibration steps.",
                    figure_refs=[],
                )
            )
            # ...and a decoy section about something unrelated
            db.add(
                DeviceDocumentSection(
                    id=section_color_id,
                    document_id=document_id,
                    section_name="Button Color",
                    section_type="text",
                    heading_level=1,
                    section_order=2,
                    content="This section describes the button color options for the interface.",
                    figure_refs=[],
                )
            )
            ref_content = "How to calibrate the sensor after wiring it up."
            db.add(
                DocumentTemplate(
                    id=ref_section_id,
                    template_name="ref",
                    source_doc_id=reference_id,
                    section_name="Sensor Calibration Procedure",
                    section_order=1,
                    content=ref_content,
                    embedding=_keyword_vector(ref_content),
                )
            )
            await db.commit()

            chunk_count = await chunk_service.generate_and_store_chunks(db, document_id)

            matches = await reference_bge_embedding.find_matching_device_chunks(
                db, ref_section_id, document_id, k=5
            )
            return chunk_count, matches

    try:
        chunk_count, matches = loop.run_until_complete(_run())

        assert chunk_count == 2  # one chunk per device section
        assert len(matches) == 2
        # the sensor/calibration chunk should rank first (highest similarity)
        assert "sensor" in matches[0]["chunk_text"].lower()
        assert matches[0]["similarity"] > matches[1]["similarity"]
    finally:
        async def _cleanup():
            async with session_factory() as db:
                await db.execute(
                    delete(DocumentChunk).where(DocumentChunk.device_document_id == document_id)
                )
                await db.execute(
                    delete(DeviceDocumentSection).where(
                        DeviceDocumentSection.document_id == document_id
                    )
                )
                await db.execute(delete(DeviceDocument).where(DeviceDocument.id == document_id))
                await db.execute(delete(Device).where(Device.id == device_id))
                await db.execute(
                    delete(DocumentTemplate).where(DocumentTemplate.source_doc_id == reference_id)
                )
                await db.execute(
                    delete(ReferenceDocument).where(ReferenceDocument.id == reference_id)
                )
                await db.commit()

        loop.run_until_complete(_cleanup())
