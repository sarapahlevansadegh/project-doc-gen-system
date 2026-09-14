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
    """Regression test for the real bug found in manual testing: the
    device document contains its own near-identical table (same rows,
    same blank Indicator Light cells for the same conditions). A flat
    'does this value appear anywhere in the device excerpts' check would
    wrongly accept row 1's real 'Color: Red' as 'evidence' for row 2,
    since both rows live in the same atomic table chunk. Row-to-row,
    column-to-column comparison against the device's own table should
    correctly find that the device's row 2 ALSO has a blank Indicator
    Light cell, and revert."""
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = (
        "| No. | Priority | Condition | Indicator Light |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | High | Start button pressed | Color: Red |\n"
        "| 2 | High | Laser module over temperature |  |\n"
        "| 4 | Medium | Interlock not connected | Color: Yellow |\n"
    )
    # the model filled row 2's empty cell with row 1's color, and left
    # everything else untouched
    hallucinated = (
        "| No. | Priority | Condition | Indicator Light |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | High | Start button pressed | Color: Red |\n"
        "| 2 | High | Laser module over temperature | Color: Red |\n"
        "| 4 | Medium | Interlock not connected | Color: Yellow |\n"
    )
    # the device document's OWN near-identical table - same blank cell for
    # row 2, retrieved as one atomic chunk (tables are never split - see
    # rag/chunker.py)
    device_table_chunk = (
        "Errors and Warnings > Alarms\n\n"
        "| No. | Priority | Condition | Indicator Light |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | High | Start button pressed | Color: Red |\n"
        "| 2 | High | Laser module over temperature |  |\n"
        "| 4 | Medium | Interlock not connected | Color: Yellow |\n"
    )
    matches = [{"chunk_text": device_table_chunk, "similarity": 0.9}]

    sanitized, reverted = _sanitize_table_against_hallucination(original, hallucinated, matches)

    assert reverted == 1
    rows = [r.strip() for r in sanitized.splitlines()]
    assert "| 2 | High | Laser module over temperature |  |" in rows
    assert "| 1 | High | Start button pressed | Color: Red |" in rows
    assert "| 4 | Medium | Interlock not connected | Color: Yellow |" in rows


def test_sanitize_table_accepts_change_traceable_to_device_excerpts():
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = "| Param | Value |\n| --- | --- |\n| Power | 5 W |\n"
    updated = "| Param | Value |\n| --- | --- |\n| Power | 8 W |\n"
    matches = [{"chunk_text": "The laser supports up to 8 W peak power.", "similarity": 0.8}]

    sanitized, reverted = _sanitize_table_against_hallucination(original, updated, matches)

    assert reverted == 0
    assert "8 W" in sanitized


def test_sanitize_table_prefers_device_table_row_over_loose_chunk_match():
    """When a device table row DOES match this reference row but its own
    value for the changed column disagrees, that should win over a
    coincidental substring match elsewhere in the same chunk's raw text."""
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = "| Condition | Value |\n| --- | --- |\n| Laser module over temperature | 35 C |\n"
    hallucinated = (
        "| Condition | Value |\n| --- | --- |\n| Laser module over temperature | 40 C |\n"
    )
    # the device's own table row says 35 C (unchanged), even though the
    # string "40 C" happens to appear elsewhere in the same chunk's prose
    device_chunk = (
        "Spec notes: values above 40 C are out of range for other components.\n\n"
        "| Condition | Value |\n| --- | --- |\n| Laser module over temperature | 35 C |\n"
    )
    matches = [{"chunk_text": device_chunk, "similarity": 0.85}]

    sanitized, reverted = _sanitize_table_against_hallucination(original, hallucinated, matches)

    assert reverted == 1
    assert "| Laser module over temperature | 35 C |" in sanitized


def test_sanitize_table_shape_mismatch_passes_through_unchanged():
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    restructured = "| A | B | C |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n"

    sanitized, reverted = _sanitize_table_against_hallucination(original, restructured, [])

    assert reverted == 0
    assert sanitized == restructured


def test_sanitize_table_rejected_when_reference_section_has_no_table():
    """Reproduces the failure seen against the real VL8 documents: three
    prose-only architecture sections (no table in the reference at all)
    each got the device document's own "Errors and Warnings" table pasted
    in verbatim as new_table_markdown. There is no reference table to
    anchor row/column comparisons against, so the only safe outcome is
    full rejection - never a partial accept."""
    from services.document_diff_planner import _sanitize_table_against_hallucination

    original = (
        "According to general system architecture, interaction control "
        "logic defines the procedures through which the user interacts "
        "with the device."
    )
    fabricated_table = (
        "| No. | Priority | Alarm/Warning Condition | Indicator Light |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | High | Tapping Start Button | Color: Red |\n"
    )
    device_chunk = (
        "Errors and Warnings Display\n\n" + fabricated_table
    )
    matches = [{"chunk_text": device_chunk, "similarity": 0.9}]

    sanitized, reverted = _sanitize_table_against_hallucination(
        original, fabricated_table, matches
    )

    assert sanitized is None
    assert reverted == -1


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


def test_specification_key_groups_by_label_before_separator():
    from services.document_diff_planner import _specification_key

    assert _specification_key("GUI Software Version: 7.0.0.7650") == "gui software version"
    assert _specification_key("GUI Software Version: 8.1.0.1000") == "gui software version"
    assert _specification_key("Driver Software Version = 01") == "driver software version"
    # no recognized separator at all -> None, not a fallback key - see
    # test_specification_key_bare_label_does_not_collide_with_real_key below
    # for why a fallback used to be wrong
    assert _specification_key("Max Power 8 W") is None


def test_specification_key_bare_label_does_not_collide_with_real_key():
    """Regression test for a real false positive found testing against the
    VL8 golden fixture: a bare label with no separator ("Duty Cycle")
    must not produce a key at all, because an earlier version fell back
    to the whole lowercased value as its own "key" - which happened to be
    IDENTICAL to the derived key of a completely unrelated, separator-
    having value ("Duty Cycle: Adjustable from 5% to 100%..." also
    normalizes to "duty cycle"), flagging two unrelated extractions as a
    contradiction.
    """
    from services.document_diff_planner import _specification_key

    assert _specification_key("Duty Cycle") is None
    assert _specification_key("Duty Cycle: Adjustable from 5% to 100% in 5% increments.") == (
        "duty cycle"
    )


def test_specification_key_rejects_generic_single_word_key():
    """Regression test for the other real false positive: "Power" recurs
    across unrelated facts in the same document (a table's byte-field
    description, an actual output-power limit, ...) - too generic a label
    to trust as identifying "the same spec", so it must not form a key at
    all (same _MIN_ANCHOR_LEN-style specificity threshold as the table
    guardrail above)."""
    from services.document_diff_planner import _specification_key

    assert _specification_key("Power: up to 8 watts") is None
    assert _specification_key("Power: Value of output Power (W) for each wavelength") is None


def test_check_ontology_consistency_flags_conflicting_specification_values(_db_session):
    loop, session_factory = _db_session

    from models.device import Device
    from models.ontology import OntologyEntity
    from services.document_diff_planner import check_ontology_consistency
    from sqlalchemy import delete

    device_id = uuid.uuid4()

    async def _run():
        async with session_factory() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-ONTO-CONSISTENCY-1"))
            await db.flush()
            db.add_all(
                [
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="GUI Software Version: 7.0.0.7650",
                    ),
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="GUI Software Version: 8.1.0.1000",
                    ),
                    # a different, non-conflicting spec - must not be flagged
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="Driver Software Version: 01",
                    ),
                    # a bare label with no separator alongside an unrelated
                    # separator-having value that happens to start with the
                    # same word - must NOT be flagged (real false positive
                    # found against the VL8 golden fixture)
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="Duty Cycle",
                    ),
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="Duty Cycle: Adjustable from 5% to 100% in 5% increments.",
                    ),
                    # a generic single-word label repeated for unrelated
                    # facts - must NOT be flagged (the other real false
                    # positive found against the same fixture)
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="Power: up to 8 watts",
                    ),
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="Power: Value of output Power (W) for each wavelength",
                    ),
                    # a different entity_type entirely - must be ignored
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Device", value="VL8",
                    ),
                ]
            )
            await db.commit()
            return await check_ontology_consistency(db, device_id)

    try:
        issues = loop.run_until_complete(_run())
        assert len(issues) == 1
        issue = issues[0]
        assert issue.entity_type == "Specification"
        assert issue.key == "gui software version"
        assert issue.values == (
            "GUI Software Version: 7.0.0.7650",
            "GUI Software Version: 8.1.0.1000",
        )
    finally:
        async def _cleanup():
            async with session_factory() as db:
                await db.execute(delete(OntologyEntity).where(OntologyEntity.device_id == device_id))
                await db.execute(delete(Device).where(Device.id == device_id))
                await db.commit()

        loop.run_until_complete(_cleanup())


def test_check_ontology_consistency_returns_empty_when_no_conflict(_db_session):
    loop, session_factory = _db_session

    from models.device import Device
    from models.ontology import OntologyEntity
    from services.document_diff_planner import check_ontology_consistency
    from sqlalchemy import delete

    device_id = uuid.uuid4()

    async def _run():
        async with session_factory() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-ONTO-CONSISTENCY-2"))
            await db.flush()
            db.add(
                OntologyEntity(
                    id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                    value="GUI Software Version: 7.0.0.7650",
                )
            )
            await db.commit()
            return await check_ontology_consistency(db, device_id)

    try:
        issues = loop.run_until_complete(_run())
        assert issues == []
    finally:
        async def _cleanup():
            async with session_factory() as db:
                await db.execute(delete(OntologyEntity).where(OntologyEntity.device_id == device_id))
                await db.execute(delete(Device).where(Device.id == device_id))
                await db.commit()

        loop.run_until_complete(_cleanup())


def test_build_document_plan_includes_ontology_warnings_for_the_device(_db_session):
    """build_document_plan() must surface ontology consistency warnings for
    the device_document's device alongside the section plans themselves -
    not just via the separate GET /devices/{device_id}/ontology/consistency
    endpoint. Uses an empty-content reference section so build_section_plan
    skips the LLM entirely (see test_empty_section_skips_llm above) -
    this test is only about the ontology_warnings wiring, not plan quality.
    """
    loop, session_factory = _db_session

    from models.device import Device
    from models.device_document import DeviceDocument
    from models.ontology import OntologyEntity
    from models.template import DocumentTemplate, ReferenceDocument
    from services.document_diff_planner import build_document_plan
    from sqlalchemy import delete

    device_id = uuid.uuid4()
    document_id = uuid.uuid4()
    reference_id = uuid.uuid4()
    ref_section_id = uuid.uuid4()

    async def _run():
        async with session_factory() as db:
            db.add(Device(id=device_id, name="Test Device", document_code="TST-ONTO-PLAN-1"))
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
                DocumentTemplate(
                    id=ref_section_id, template_name="r", source_doc_id=reference_id,
                    section_name="Intro", section_order=1, content="",
                )
            )
            db.add_all(
                [
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="GUI Software Version: 7.0.0.7650",
                    ),
                    OntologyEntity(
                        id=uuid.uuid4(), device_id=device_id, entity_type="Specification",
                        value="GUI Software Version: 8.1.0.1000",
                    ),
                ]
            )
            await db.commit()

            return await build_document_plan(db, reference_id, document_id)

    try:
        plan = loop.run_until_complete(_run())

        assert len(plan.section_plans) == 1
        assert plan.section_plans[0].section_name == "Intro"
        assert plan.section_plans[0].changed is False  # empty content -> untouched

        assert len(plan.ontology_warnings) == 1
        assert plan.ontology_warnings[0].key == "gui software version"
        assert plan.ontology_warnings[0].values == (
            "GUI Software Version: 7.0.0.7650",
            "GUI Software Version: 8.1.0.1000",
        )
    finally:
        async def _cleanup():
            async with session_factory() as db:
                await db.execute(delete(OntologyEntity).where(OntologyEntity.device_id == device_id))
                await db.execute(delete(DocumentTemplate).where(DocumentTemplate.id == ref_section_id))
                await db.execute(
                    delete(ReferenceDocument).where(ReferenceDocument.id == reference_id)
                )
                await db.execute(delete(DeviceDocument).where(DeviceDocument.id == document_id))
                await db.execute(delete(Device).where(Device.id == device_id))
                await db.commit()

        loop.run_until_complete(_cleanup())


def test_build_document_plan_ontology_warnings_empty_when_device_document_unknown(_db_session):
    """Fail-soft regression test: a device_document_id that doesn't
    resolve to any DeviceDocument row (e.g. deleted, or a bad id) must
    not crash plan generation - it just means no ontology warnings are
    available, same fail-soft spirit as ontology_extraction_service.py."""
    loop, session_factory = _db_session

    from models.template import DocumentTemplate, ReferenceDocument
    from services.document_diff_planner import build_document_plan
    from sqlalchemy import delete

    reference_id = uuid.uuid4()
    ref_section_id = uuid.uuid4()
    unknown_document_id = uuid.uuid4()

    async def _run():
        async with session_factory() as db:
            db.add(
                ReferenceDocument(
                    id=reference_id, filename="r.docx", template_name="r",
                    embedding_model="BAAI/bge-base-en-v1.5", embedding_dimension=EMBED_DIM,
                )
            )
            await db.flush()
            db.add(
                DocumentTemplate(
                    id=ref_section_id, template_name="r", source_doc_id=reference_id,
                    section_name="Intro", section_order=1, content="",
                )
            )
            await db.commit()

            return await build_document_plan(db, reference_id, unknown_document_id)

    try:
        plan = loop.run_until_complete(_run())
        assert len(plan.section_plans) == 1
        assert plan.ontology_warnings == []
    finally:
        async def _cleanup():
            async with session_factory() as db:
                await db.execute(delete(DocumentTemplate).where(DocumentTemplate.id == ref_section_id))
                await db.execute(
                    delete(ReferenceDocument).where(ReferenceDocument.id == reference_id)
                )
                await db.commit()

        loop.run_until_complete(_cleanup())
