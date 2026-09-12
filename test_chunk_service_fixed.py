"""Integration test for rag/chunk_service.generate_and_store_chunks.

Runs against a real Postgres connection (skipped if unavailable), following
the same DB-availability-check pattern as tests/test_rag.py. The embedding
model itself is monkeypatched out (fake zero-vector service) so this test
doesn't need to load bge-base-en-v1.5 / torch - it's testing the chunk
generation + figure_refs linkage, not embedding quality.

Uses a plain async test (no manual asyncio.new_event_loop()) - this relies
on pytest-asyncio's session-scoped loop (see pyproject.toml), the same loop
core.database's module-level engine singleton is created on. Manually
spinning up a second event loop here, independent of that shared loop, is
exactly the pattern that produced "attached to a different loop" errors in
test_auth.py; this file no longer needs it now that the loop is unified
project-wide.
"""
from __future__ import annotations

import uuid

import pytest

EMBED_DIM = 768


class _FakeEmbeddingService:
    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        return [[0.0] * EMBED_DIM for _ in texts]


async def _db_available() -> bool:
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_generate_and_store_chunks_links_figures(monkeypatch):
    try:
        from core.database import AsyncSessionLocal
    except ModuleNotFoundError:
        pytest.skip("async app stack unavailable")

    if not await _db_available():
        pytest.skip("Postgres unavailable")

    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.document_chunk import DocumentChunk
    from rag import chunk_service
    from sqlalchemy import delete, select

    monkeypatch.setattr(
        chunk_service, "get_device_embedding_service", lambda: _FakeEmbeddingService()
    )
    monkeypatch.setattr(chunk_service, "bge_token_counter", lambda: (lambda t: len(t.split())))

    device_id = uuid.uuid4()
    document_id = uuid.uuid4()
    section_with_figure_id = uuid.uuid4()
    empty_section_id = uuid.uuid4()

    figure = {
        "rel_id": "rId5",
        "alt_text": "Sensor wiring diagram",
        "image_path": "/data/device_documents/images/some-doc/rId5.png",
    }

    try:
        async with AsyncSessionLocal() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-1"))
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
            db.add(
                DeviceDocumentSection(
                    id=empty_section_id,
                    document_id=document_id,
                    section_name="Standard Requirements",
                    section_type="text",
                    heading_level=1,
                    parent_section=None,
                    section_order=1,
                    content="",
                    figure_refs=[],
                )
            )
            db.add(
                DeviceDocumentSection(
                    id=section_with_figure_id,
                    document_id=document_id,
                    section_name="Settings Page",
                    section_type="figure",
                    heading_level=2,
                    parent_section="Standard Requirements",
                    section_order=2,
                    content="The settings page shows a sensor wiring diagram below.",
                    figure_refs=[figure],
                )
            )
            await db.commit()

            count = await chunk_service.generate_and_store_chunks(db, document_id)

            result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.device_document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
            chunks = result.scalars().all()

        # the empty section produced no chunk of its own
        assert count == len(chunks) == 1

        chunk = chunks[0]
        assert chunk.section_id == section_with_figure_id
        # breadcrumb from the empty parent section is present
        assert chunk.chunk_text.startswith("Standard Requirements > Settings Page")
        # the figure is linked directly on the chunk, not just the section
        assert chunk.figure_refs == [figure]
        assert chunk.embedding is not None
    finally:
        async with AsyncSessionLocal() as db:
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
            await db.commit()
