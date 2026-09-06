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


def test_extract_markdown_table_drops_separator_row():
    from services.document_diff_planner import _extract_markdown_table

    text = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"
    rows = _extract_markdown_table(text)
    assert rows == [["A", "B"], ["1", "2"], ["3", "4"]]


def test_sanitize_table_reverts_unverifiable_cell_but_keeps_verifiable_one():
    """Regression test for a real bug: the model filled an empty
    'Indicator Light' cell with an inferred color (pattern-matched from
    the row's priority) even though neither document stated it, while a
    genuinely-unchanged cell with the same non-empty value should NOT be
    flagged as a hallucination just because it isn't literally repeated in
    the device excerpts word-for-word this time."""
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = (
        "| No. | Priority | Condition | Indicator Light |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | High | Start button pressed | Color: Red |\n"
        "| 2 | High | Over temperature |  |\n"
        "| 4 | Medium | Interlock not connected | Color: Yellow |\n"
    )
    # the model filled row 2's empty cell with an invented color, and left
    # everything else untouched
    hallucinated = (
        "| No. | Priority | Condition | Indicator Light |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | High | Start button pressed | Color: Red |\n"
        "| 2 | High | Over temperature | Color: Red |\n"
        "| 4 | Medium | Interlock not connected | Color: Yellow |\n"
    )
    device_excerpts = "Over temperature interrupts laser emission immediately."

    sanitized, reverted = _sanitize_table_against_hallucination(
        original, hallucinated, device_excerpts
    )

    assert reverted == 1
    rows = [r.strip() for r in sanitized.splitlines()]
    assert "| 2 | High | Over temperature |  |" in rows
    # untouched cells (including the unchanged "Color: Red"/"Color: Yellow"
    # that were already in the reference) are preserved, not flagged
    assert "| 1 | High | Start button pressed | Color: Red |" in rows
    assert "| 4 | Medium | Interlock not connected | Color: Yellow |" in rows


def test_sanitize_table_accepts_change_traceable_to_device_excerpts():
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = "| Param | Value |\n| --- | --- |\n| Power | 5 W |\n"
    updated = "| Param | Value |\n| --- | --- |\n| Power | 8 W |\n"
    device_excerpts = "The laser supports up to 8 W peak power."

    sanitized, reverted = _sanitize_table_against_hallucination(original, updated, device_excerpts)

    assert reverted == 0
    assert "8 W" in sanitized


def test_sanitize_table_shape_mismatch_passes_through_unchanged():
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    restructured = "| A | B | C |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n"

    sanitized, reverted = _sanitize_table_against_hallucination(original, restructured, "")

    assert reverted == 0
    assert sanitized == restructured


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


def test_good_match_with_hallucinated_table_cell_gets_reverted(_db_session, monkeypatch):
    """End-to-end: build_section_plan() itself applies the sanitizer, not
    just the helper function in isolation."""
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

    ref_table = (
        "| No. | Condition | Indicator Light |\n"
        "| --- | --- | --- |\n"
        "| 1 | Start pressed | Color: Red |\n"
        "| 2 | Over temperature |  |\n"
    )
    # LLM invents a color for row 2 that neither document states
    hallucinated_table = (
        "| No. | Condition | Indicator Light |\n"
        "| --- | --- | --- |\n"
        "| 1 | Start pressed | Color: Red |\n"
        "| 2 | Over temperature | Color: Red |\n"
    )
    llm_response = json.dumps(
        {
            "changed": True,
            "reason": "Device document addresses the over-temperature condition.",
            "new_paragraphs": None,
            "new_table_markdown": hallucinated_table,
        }
    )
    fake_llm = _FakeLLM(responses=[llm_response])

    async def _run():
        async with session_factory() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-6"))
            db.add(
                DeviceDocument(
                    id=document_id, device_id=device_id, filename="d6.docx",
                    storage_path="/tmp/d6.docx", file_size=1,
                )
            )
            db.add(
                ReferenceDocument(
                    id=reference_id, filename="r6.docx", template_name="r6",
                    embedding_model="BAAI/bge-base-en-v1.5", embedding_dimension=EMBED_DIM,
                )
            )
            await db.flush()

            db.add(
                DeviceDocumentSection(
                    id=section_id, document_id=document_id,
                    section_name="Alarms", section_type="text",
                    heading_level=1, section_order=1,
                    content="Sensor calibration section. Over temperature interrupts laser emission immediately.",
                    figure_refs=[],
                )
            )
            ref_section = DocumentTemplate(
                id=ref_section_id, template_name="r6", source_doc_id=reference_id,
                section_name="Alarms Table", section_order=1,
                content=ref_table,
                embedding=_keyword_vector("sensor calibration " + ref_table),
            )
            db.add(ref_section)
            await db.commit()

            await chunk_service.generate_and_store_chunks(db, document_id)
            await db.refresh(ref_section)

            return await build_section_plan(db, ref_section, document_id, fake_llm)

    try:
        plan = loop.run_until_complete(_run())

        assert plan.new_table_markdown is not None
        assert "reverted to the reference value" in plan.reason
        rows = [r.strip() for r in plan.new_table_markdown.splitlines()]
        assert "| 2 | Over temperature |  |" in rows
        assert "| 1 | Start pressed | Color: Red |" in rows
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
