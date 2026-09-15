"""Tests for services/document_generator.py (Phase 5).

Pure-logic tests (markdown table parsing, paragraph/table cell editing,
live section extraction) run without a database. The end-to-end test is
DB-gated and hermetic like test_device_upload_pipeline.py: no real LLM or
embedding model, both monkeypatched out.
"""
from __future__ import annotations

import io

import pytest
from docx import Document as DocxDocument


def _make_docx_bytes() -> bytes:
    doc = DocxDocument()
    doc.add_heading("1. Architecture of Software", level=1)
    doc.add_paragraph("The device runs a layered software architecture.")
    doc.add_heading("2. Errors and Warnings", level=1)
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "No."
    table.rows[0].cells[1].text = "Condition"
    table.rows[1].cells[0].text = "1"
    table.rows[1].cells[1].text = "Over temperature."
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------- pure-logic tests ----------


def test_parse_markdown_table_skips_header_separator():
    from services.document_generator import _parse_markdown_table

    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n"
    rows = _parse_markdown_table(md)

    assert rows == [["A", "B"], ["1", "2"], ["3", "4"]]


def test_apply_paragraphs_replaces_text_in_order():
    from services.document_generator import _apply_paragraphs

    doc = DocxDocument()
    p1 = doc.add_paragraph("old one")
    p2 = doc.add_paragraph("old two")

    _apply_paragraphs([p1, p2], ["new one", "new two"])

    assert p1.text == "new one"
    assert p2.text == "new two"


def test_apply_paragraphs_appends_extra_text_rather_than_dropping():
    from services.document_generator import _apply_paragraphs

    doc = DocxDocument()
    p1 = doc.add_paragraph("old")

    _apply_paragraphs([p1], ["new", "extra sentence"])

    assert "new" in p1.text
    assert "extra sentence" in p1.text


def test_apply_table_replaces_matching_shape():
    from services.document_generator import _apply_table

    doc = DocxDocument()
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "No."
    table.rows[0].cells[1].text = "Condition"
    table.rows[1].cells[0].text = "1"
    table.rows[1].cells[1].text = "Over temperature."

    new_md = "| No. | Condition |\n| --- | --- |\n| 1 | Battery low. |\n"
    _apply_table(table, new_md)

    assert table.rows[1].cells[1].text == "Battery low."
    assert table.rows[1].cells[0].text == "1"  # unaddressed cell untouched


def test_apply_table_leaves_unchanged_on_shape_mismatch():
    from services.document_generator import _apply_table

    doc = DocxDocument()
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "No."
    table.rows[0].cells[1].text = "Condition"
    table.rows[1].cells[0].text = "1"
    table.rows[1].cells[1].text = "Over temperature."

    # 3 columns in the replacement vs 2 in the original - shape mismatch
    new_md = "| No. | Condition | Extra |\n| --- | --- | --- |\n| 1 | X | Y |\n"
    _apply_table(table, new_md)

    assert table.rows[1].cells[1].text == "Over temperature."


def test_extract_docx_live_groups_blocks_by_heading(tmp_path):
    from rag.extractor import extract_docx_live
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    path = tmp_path / "ref.docx"
    path.write_bytes(_make_docx_bytes())

    document, sections = extract_docx_live(path)

    names = [s.title for s in sections]
    assert "1. Architecture of Software" in names
    assert "2. Errors and Warnings" in names

    arch = next(s for s in sections if s.title == "1. Architecture of Software")
    assert any(isinstance(b, Paragraph) for b in arch.blocks)
    assert "layered software architecture" in arch.text

    errors = next(s for s in sections if s.title == "2. Errors and Warnings")
    assert any(isinstance(b, Table) for b in errors.blocks)
    assert "Over temperature" in errors.text


# ---------- DB-gated end-to-end test ----------


def _fake_llm_generate(self, prompt: str, max_tokens: int = 800, temperature: float = 0.1) -> str:
    if "layered software architecture" in prompt:
        return (
            '{"changed": true, "reason": "device-specific value provided", '
            '"new_paragraphs": ["The VL8 runs a layered software architecture."], '
            '"new_table_markdown": null}'
        )
    return '{"changed": false, "reason": "no device-specific content", "new_paragraphs": null, "new_table_markdown": null}'


async def _fake_embed_text(text: str) -> list[float]:
    return [1.0] + [0.0] * 767


async def _db_ok(AsyncSessionLocal):
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))


def test_generate_final_document_applies_changed_section_only(tmp_path):
    try:
        from agent.llm import LLMClient
        from core.database import AsyncSessionLocal
        from models.device_document import DeviceDocument
        from services import document_generator
    except ModuleNotFoundError:
        pytest.skip("async app stack unavailable")

    import asyncio
    import uuid

    from models.template import ReferenceDocument

    loop = asyncio.new_event_loop()
    try:
        try:
            loop.run_until_complete(_db_ok(AsyncSessionLocal))
        except Exception as exc:
            if "connect" in str(exc).lower():
                pytest.skip("Postgres unavailable")
            raise
    finally:
        loop.close()

    ref_path = tmp_path / "reference.docx"
    ref_path.write_bytes(_make_docx_bytes())

    reference_doc = ReferenceDocument(
        id=uuid.uuid4(),
        filename="reference.docx",
        template_name="reference",
        storage_path=str(ref_path),
        embedding_model="bge-base-en-v1.5",
        embedding_dimension=768,
    )
    device_document_id = uuid.uuid4()

    real_generate = LLMClient.generate
    real_embed_text = document_generator.embed_text
    LLMClient.generate = _fake_llm_generate
    document_generator.embed_text = _fake_embed_text

    async def _run():
        async with AsyncSessionLocal() as db:
            from models.device import Device
            from models.device_document import DeviceDocumentSection
            from models.document_chunk import DocumentChunk

            device_id = uuid.uuid4()
            db.add(Device(id=device_id, name="VL8", safety_class="B"))
            db.add(reference_doc)
            await db.flush()  # Device/ReferenceDocument must exist before
            # DeviceDocument/DocumentChunk insert - don't rely on
            # autoflush's automatic FK-based insert ordering across
            # unrelated add() calls in one commit.
            db.add(
                DeviceDocument(
                    id=device_document_id,
                    device_id=device_id,
                    filename="device.docx",
                    storage_path=str(tmp_path / "device.docx"),
                    file_size=1,
                )
            )
            device_section_id = uuid.uuid4()
            db.add(
                DeviceDocumentSection(
                    id=device_section_id,
                    document_id=device_document_id,
                    section_name="Architecture",
                    section_type="TEXT",
                    section_order=1,
                    content="The VL8 device architecture description.",
                )
            )
            await db.flush()  # DeviceDocumentSection must exist before
            # DocumentChunk, same reasoning as above
            db.add(
                DocumentChunk(
                    section_id=device_section_id,
                    device_document_id=device_document_id,
                    chunk_text="The VL8 device architecture description.",
                    chunk_index=0,
                    embedding=[1.0] + [0.0] * 767,
                )
            )
            await db.commit()

            try:
                result = await document_generator.generate_final_document(
                    db, reference_doc, device_document_id, output_dir=tmp_path / "out"
                )
            finally:
                await db.delete(reference_doc)
                dd = await db.get(DeviceDocument, device_document_id)
                if dd is not None:
                    await db.delete(dd)
                dev = await db.get(Device, device_id)
                if dev is not None:
                    await db.delete(dev)
                await db.commit()
        return result

    try:
        result = asyncio.run(_run())
    finally:
        LLMClient.generate = real_generate
        document_generator.embed_text = real_embed_text

    output_path = result["output_path"]
    assert output_path.is_file()

    generated = DocxDocument(str(output_path))
    paragraph_texts = [p.text for p in generated.paragraphs]
    assert "The VL8 runs a layered software architecture." in paragraph_texts
    # the errors/warnings table's cells were left untouched (LLM said no change)
    assert generated.tables[0].rows[1].cells[1].text == "Over temperature."
