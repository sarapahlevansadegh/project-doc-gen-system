"""Tests for services/document_diff_planner.py.

Uses a real Postgres connection for the matching step (skipped if
unavailable, same pattern as the other rag integration tests) and a fake
LLMClient (generate_fn injection, same pattern as tests/test_journey.py's
_fake_llm) so no real model call is made.
"""
from __future__ import annotations

import asyncio
import json
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


class _FakeLLM:
    """Records prompts it was called with; returns a queued response per call."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.2) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def _seed(db_add, device_id, document_id, reference_id, section_sensor_id, ref_section_id, ref_content):
    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.template import DocumentTemplate, ReferenceDocument

    db_add(Device(id=device_id, name="Test Device", document_code="TST-3"))
    db_add(
        DeviceDocument(
            id=document_id,
            device_id=device_id,
            filename="test.docx",
            storage_path="/tmp/test3.docx",
            file_size=1,
        )
    )
    db_add(
        ReferenceDocument(
            id=reference_id,
            filename="ref3.docx",
            template_name="ref3",
            embedding_model="BAAI/bge-base-en-v1.5",
            embedding_dimension=EMBED_DIM,
        )
    )
    return DeviceDocumentSection, DocumentTemplate, ref_content


def test_empty_section_skips_llm(_db_session):
    loop, session_factory = _db_session
    from models.template import DocumentTemplate, ReferenceDocument
    from services.document_diff_planner import build_section_plan

    reference_id = uuid.uuid4()
    section_id = uuid.uuid4()
    fake_llm = _FakeLLM(responses=[])

    async def _run():
        async with session_factory() as db:
            db.add(
                ReferenceDocument(
                    id=reference_id, filename="r.docx", template_name="r",
                    embedding_model="BAAI/bge-base-en-v1.5", embedding_dimension=EMBED_DIM,
                )
            )
            await db.flush()
            section = DocumentTemplate(
                id=section_id, template_name="r", source_doc_id=reference_id,
                section_name="Empty Heading", section_order=1, content="",
            )
            db.add(section)
            await db.commit()
            await db.refresh(section)
            return await build_section_plan(db, section, uuid.uuid4(), fake_llm)

    plan = loop.run_until_complete(_run())
    assert plan.changed is False
    assert fake_llm.prompts == []  # never called the LLM for an empty section


def test_no_match_skips_llm_and_leaves_unchanged(_db_session):
    loop, session_factory = _db_session
    from models.template import DocumentTemplate, ReferenceDocument
    from services.document_diff_planner import build_section_plan

    reference_id = uuid.uuid4()
    section_id = uuid.uuid4()
    fake_llm = _FakeLLM(responses=[])

    async def _run():
        async with session_factory() as db:
            db.add(
                ReferenceDocument(
                    id=reference_id, filename="r.docx", template_name="r",
                    embedding_model="BAAI/bge-base-en-v1.5", embedding_dimension=EMBED_DIM,
                )
            )
            await db.flush()
            section = DocumentTemplate(
                id=section_id, template_name="r", source_doc_id=reference_id,
                section_name="Unrelated", section_order=1,
                content="Generic boilerplate about paperwork.",
                embedding=_keyword_vector("paperwork filing forms"),
            )
            db.add(section)
            await db.commit()
            await db.refresh(section)
            # a device_document_id with no chunks at all -> no matches
            return await build_section_plan(db, section, uuid.uuid4(), fake_llm)

    plan = loop.run_until_complete(_run())
    assert plan.changed is False
    assert "No sufficiently similar" in plan.reason
    assert fake_llm.prompts == []


def test_good_match_calls_llm_and_parses_plan(_db_session, monkeypatch):
    loop, session_factory = _db_session

    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.template import DocumentTemplate, ReferenceDocument
    from rag import chunk_service
    from services.document_diff_planner import build_section_plan
    from sqlalchemy import delete
    from models.document_chunk import DocumentChunk

    monkeypatch.setattr(
        chunk_service, "get_device_embedding_service", lambda: _FakeEmbeddingService()
    )
    monkeypatch.setattr(chunk_service, "bge_token_counter", lambda: (lambda t: len(t.split())))

    device_id = uuid.uuid4()
    document_id = uuid.uuid4()
    section_sensor_id = uuid.uuid4()
    reference_id = uuid.uuid4()
    ref_section_id = uuid.uuid4()

    llm_response = json.dumps(
        {
            "changed": True,
            "reason": "Device document specifies the sensor calibration interval.",
            "new_paragraphs": ["Calibrate the sensor every 30 days per device spec."],
            "new_table_markdown": None,
        }
    )
    fake_llm = _FakeLLM(responses=[llm_response])

    async def _run():
        async with session_factory() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-4"))
            db.add(
                DeviceDocument(
                    id=document_id, device_id=device_id, filename="d.docx",
                    storage_path="/tmp/d.docx", file_size=1,
                )
            )
            db.add(
                ReferenceDocument(
                    id=reference_id, filename="r.docx", template_name="r",
                    embedding_model="BAAI/bge-base-en-v1.5", embedding_dimension=EMBED_DIM,
                )
            )
            await db.flush()

            db.add(
                DeviceDocumentSection(
                    id=section_sensor_id, document_id=document_id,
                    section_name="Sensor Calibration", section_type="text",
                    heading_level=1, section_order=1,
                    content="Sensor calibration must be done every 30 days.",
                    figure_refs=[],
                )
            )
            ref_content = "Calibrate the sensor periodically."
            ref_section = DocumentTemplate(
                id=ref_section_id, template_name="r", source_doc_id=reference_id,
                section_name="Sensor Calibration Procedure", section_order=1,
                content=ref_content, embedding=_keyword_vector(ref_content + " calibration sensor"),
            )
            db.add(ref_section)
            await db.commit()

            await chunk_service.generate_and_store_chunks(db, document_id)
            await db.refresh(ref_section)

            plan = await build_section_plan(db, ref_section, document_id, fake_llm)
            return plan

    try:
        plan = loop.run_until_complete(_run())

        assert len(fake_llm.prompts) == 1
        assert "Calibrate the sensor periodically." in fake_llm.prompts[0]
        assert plan.changed is True
        assert plan.new_paragraphs == ["Calibrate the sensor every 30 days per device spec."]
        assert plan.new_table_markdown is None
        assert plan.best_similarity is not None and plan.best_similarity > 0
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


def test_malformed_llm_json_does_not_crash(_db_session, monkeypatch):
    loop, session_factory = _db_session

    from models.device import Device
    from models.device_document import DeviceDocument, DeviceDocumentSection
    from models.template import DocumentTemplate, ReferenceDocument
    from rag import chunk_service
    from services.document_diff_planner import build_section_plan
    from sqlalchemy import delete
    from models.document_chunk import DocumentChunk

    monkeypatch.setattr(
        chunk_service, "get_device_embedding_service", lambda: _FakeEmbeddingService()
    )
    monkeypatch.setattr(chunk_service, "bge_token_counter", lambda: (lambda t: len(t.split())))

    device_id = uuid.uuid4()
    document_id = uuid.uuid4()
    section_id = uuid.uuid4()
    reference_id = uuid.uuid4()
    ref_section_id = uuid.uuid4()

    fake_llm = _FakeLLM(responses=["this is not json"])

    async def _run():
        async with session_factory() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-5"))
            db.add(
                DeviceDocument(
                    id=document_id, device_id=device_id, filename="d.docx",
                    storage_path="/tmp/d5.docx", file_size=1,
                )
            )
            db.add(
                ReferenceDocument(
                    id=reference_id, filename="r5.docx", template_name="r5",
                    embedding_model="BAAI/bge-base-en-v1.5", embedding_dimension=EMBED_DIM,
                )
            )
            await db.flush()

            db.add(
                DeviceDocumentSection(
                    id=section_id, document_id=document_id,
                    section_name="Sensor Setup", section_type="text",
                    heading_level=1, section_order=1,
                    content="This section covers sensor wiring and calibration.",
                    figure_refs=[],
                )
            )
            ref_content = "How to calibrate the sensor."
            ref_section = DocumentTemplate(
                id=ref_section_id, template_name="r5", source_doc_id=reference_id,
                section_name="Sensor Calibration", section_order=1,
                content=ref_content, embedding=_keyword_vector(ref_content + " sensor calibration"),
            )
            db.add(ref_section)
            await db.commit()

            await chunk_service.generate_and_store_chunks(db, document_id)
            await db.refresh(ref_section)

            return await build_section_plan(db, ref_section, document_id, fake_llm)

    try:
        plan = loop.run_until_complete(_run())
        assert plan.changed is False
        assert "Could not parse" in plan.reason
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
