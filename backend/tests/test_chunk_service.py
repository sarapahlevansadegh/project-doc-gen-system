"""Integration test for rag/chunk_service.generate_and_store_chunks.

Runs against a real Postgres connection (skipped if unavailable), following
the same DB-availability-check pattern as tests/test_rag.py. The embedding
model itself is monkeypatched out (fake zero-vector service) so this test
doesn't need to load bge-base-en-v1.5 / torch - it's testing the chunk
generation + figure_refs linkage, not embedding quality.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

EMBED_DIM = 768


class _FakeEmbeddingService:
    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        return [[0.0] * EMBED_DIM for _ in texts]


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


def test_generate_and_store_chunks_links_figures(_db_session, monkeypatch):
    loop, session_factory = _db_session

    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.document_chunk import DocumentChunk
    from rag import chunk_service
    from sqlalchemy import delete

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

    async def _run():
        async with session_factory() as db:
            db.add(
                Device(id=device_id, name="Test Device", document_code="TST-1")
            )
            db.add(
                DeviceDocument(
                    id=document_id,
                    device_id=device_id,
                    filename="test.docx",
                    storage_path="/tmp/test.docx",
                    file_size=123,
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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

            from sqlalchemy import select

            result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.device_document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
            chunks = result.scalars().all()
            return count, chunks

        # cleanup regardless of outcome
    try:
        count, chunks = loop.run_until_complete(_run())

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
                await db.commit()

        loop.run_until_complete(_cleanup())
