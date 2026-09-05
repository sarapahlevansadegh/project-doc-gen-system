"""Unit tests for Markdown table serialization in rag/extractor.py.

Pure function tests (no DB, no FastAPI app) covering the flat-text -> real
Markdown table change.
"""
from __future__ import annotations

import io

from docx import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from rag.extractor import _table_to_markdown, extract_docx


def test_table_to_markdown_basic():
    rows = [
        ["Parameter", "Value", "Unit"],
        ["Sample Rate", "250", "Hz"],
        ["Resolution", "12", "bit"],
    ]
    md = _table_to_markdown(rows)
    lines = md.splitlines()

    assert lines[0] == "| Parameter | Value | Unit |"
    assert lines[1] == "| --- | --- | --- |"
    assert lines[2] == "| Sample Rate | 250 | Hz |"
    assert lines[3] == "| Resolution | 12 | bit |"


def test_table_to_markdown_escapes_pipe_in_cell():
    rows = [["Field", "Allowed values"], ["Mode", "On|Off"]]
    md = _table_to_markdown(rows)
    assert "On\\|Off" in md


def test_table_to_markdown_pads_ragged_rows():
    rows = [["A", "B", "C"], ["only one"]]
    md = _table_to_markdown(rows)
    lines = md.splitlines()
    # ragged data row is padded to the header's column count
    assert lines[2] == "| only one |  |  |"


def test_table_to_markdown_empty_table():
    assert _table_to_markdown([]) == ""


def _make_docx_with_table() -> bytes:
    doc = DocxDocument()
    doc.add_heading("1. Specifications", level=1)
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Parameter"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Sample Rate"
    table.cell(1, 1).text = "250 Hz"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_docx_section_body_contains_markdown_table(tmp_path):
    path = tmp_path / "ref.docx"
    path.write_bytes(_make_docx_with_table())

    sections = extract_docx(path)
    spec_section = next(s for s in sections if s.title == "1. Specifications")

    assert "| Parameter | Value |" in spec_section.body
    assert "| --- | --- |" in spec_section.body
    assert spec_section.has_table is True


def _make_docx_with_mislabeled_outline_paragraph() -> bytes:
    """Build a docx where a long body paragraph carries a raw outlineLvl
    element (direct formatting) without a Heading style - the pattern seen
    in real-world converted/inconsistently-templated documents."""

    def _set_outline_lvl(paragraph, level: int) -> None:
        p_pr = paragraph.paragraph_format.element.get_or_add_pPr()
        el = OxmlElement("w:outlineLvl")
        el.set(qn("w:val"), str(level))
        p_pr.append(el)

    doc = DocxDocument()

    real_heading = doc.add_paragraph("Splash Page")
    _set_outline_lvl(real_heading, 2)

    long_body = doc.add_paragraph(
        "Once the device is turned on, it should display a splash screen "
        "for a few seconds before showing the home page to the operator "
        "so they can begin configuring the treatment session parameters."
    )
    _set_outline_lvl(long_body, 2)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_long_paragraph_with_outline_level_is_not_treated_as_heading(tmp_path):
    path = tmp_path / "messy.docx"
    path.write_bytes(_make_docx_with_mislabeled_outline_paragraph())

    sections = extract_docx(path)
    titles = [s.title for s in sections]

    # the short real heading is still detected as a section...
    assert "Splash Page" in titles
    # ...but the long sentence carrying the same raw outlineLvl attribute is
    # treated as body text and folded into that section, not split into its
    # own (empty-looking) section.
    assert not any(t.startswith("Once the device is turned on") for t in titles)
    splash = next(s for s in sections if s.title == "Splash Page")
    assert "Once the device is turned on" in splash.body
