"""Reference DOCX extraction.

Parses a Word document into an ordered list of blocks while preserving the
document hierarchy (headings + levels), tables, and image metadata. No text
is blindly chopped: structure is derived from the document's own outline.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph


@dataclass
class FigureRef:
    index: int
    rel_id: str | None = None
    alt_text: str | None = None
    width: float | None = None
    height: float | None = None


@dataclass
class ExtractedBlock:
    kind: str  # "heading" | "paragraph" | "table" | "image"
    text: str = ""
    level: int | None = None
    figure: FigureRef | None = None
    table_rows: list[list[str]] | None = None


@dataclass
class ExtractedSection:
    heading_path: str
    title: str
    level: int
    body: str = ""
    blocks: list[ExtractedBlock] = field(default_factory=list)
    figures: list[FigureRef] = field(default_factory=list)
    has_table: bool = False

    @property
    def figure_refs(self) -> list[dict]:
        return [
            {
                "index": f.index,
                "rel_id": f.rel_id,
                "alt_text": f.alt_text,
                "width": f.width,
                "height": f.height,
            }
            for f in self.figures
        ]


def _iter_block_items(parent) -> Iterator:
    """Yield Paragraph and Table objects in document order."""
    if isinstance(parent, DocxDocument):
        body = parent.element.body
    elif isinstance(parent, _Cell):
        body = parent._tc
    else:
        body = parent.element
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _heading_level(paragraph: Paragraph) -> int | None:
    style_name = (paragraph.style.name or "") if paragraph.style else ""
    match = re.match(r"Heading\s+(\d+)", style_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # fallback: outline level attribute
    outline = paragraph._p.pPr
    if outline is not None:
        ol = outline.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}outlineLvl"
        )
        if ol is not None:
            return int(ol.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")) + 1
    return None


def _table_to_rows(table: Table) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        rows.append(cells)
    return rows


def _escape_md_cell(text: str) -> str:
    """Escape characters that would break Markdown table syntax."""
    return text.replace("|", "\\|").strip()


def _table_to_markdown(rows: list[list[str]]) -> str:
    """Serialize table rows into a real Markdown table.

    The first row is treated as the header (the common case for reference
    documents). Rows are padded/truncated to the header's column count so a
    ragged docx table still produces valid Markdown. Returns "" for an empty
    table so callers can join it into a section body without adding blank
    lines.
    """
    if not rows:
        return ""

    col_count = len(rows[0]) or 1

    def _pad(row: list[str]) -> list[str]:
        cells = row[:col_count] + [""] * max(0, col_count - len(row))
        return [_escape_md_cell(c) for c in cells]

    lines = ["| " + " | ".join(_pad(rows[0])) + " |"]
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(_pad(row)) + " |")
    return "\n".join(lines)


_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _collect_figure(paragraph: Paragraph, counter: list[int]) -> FigureRef | None:
    """Detect an image inside a paragraph's runs and capture metadata."""
    doc_prs = paragraph._p.findall(
        ".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"
    )
    if not doc_prs:
        return None

    doc_pr = doc_prs[0]
    counter[0] += 1

    # r:embed lives as an *attribute* on <a:blip>, not a child element, so
    # it must be read with .get() on the blip itself rather than .find().
    rel_id = None
    blip = paragraph._p.find(f".//{_A_NS}blip")
    if blip is not None:
        rel_id = blip.get(f"{_R_NS}embed")

    alt = doc_pr.get("descr") or doc_pr.get("title")
    return FigureRef(index=counter[0], rel_id=rel_id, alt_text=alt)


def extract_docx(path: str | Path) -> list[ExtractedSection]:
    """Extract reference document into a list of outline sections."""
    document = Document(str(path))

    # Walk blocks in document order, build a flat list of blocks.
    flat: list[ExtractedBlock] = []
    figure_counter = [0]

    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            level = _heading_level(block)
            if level is not None:
                flat.append(
                    ExtractedBlock(kind="heading", text=block.text.strip(), level=level)
                )
                continue
            fig = _collect_figure(block, figure_counter)
            if fig is not None:
                flat.append(ExtractedBlock(kind="image", figure=fig))
                continue
            if block.text.strip():
                flat.append(ExtractedBlock(kind="paragraph", text=block.text.strip()))
        elif isinstance(block, Table):
            rows = _table_to_rows(block)
            flat.append(
                ExtractedBlock(
                    kind="table",
                    text=_table_to_markdown(rows),
                    table_rows=rows,
                )
            )

    # Build section tree from the heading outline.
    sections: list[ExtractedSection] = []
    stack: list[ExtractedSection] = []

    for blk in flat:
        if blk.kind == "heading":
            sec = ExtractedSection(
                heading_path="", title=blk.text, level=blk.level or 1
            )
            # pop deeper-or-equal levels
            while stack and stack[-1].level >= sec.level:
                stack.pop()
            # drop the synthetic "Intro" placeholder once a real heading exists
            if stack and stack[-1].level == 0:
                stack.pop()
            if stack:
                sec.heading_path = f"{stack[-1].heading_path} > {sec.title}"
            else:
                sec.heading_path = sec.title
            stack.append(sec)
            sections.append(sec)
        else:
            if not stack:
                # content before any heading -> intro section
                sec = ExtractedSection(heading_path="Intro", title="Intro", level=0)
                sections.append(sec)
                stack.append(sec)
            target = stack[-1]
            target.blocks.append(blk)
            if blk.kind == "paragraph":
                target.body = (target.body + "\n" + blk.text).strip()
            elif blk.kind == "table":
                target.body = (target.body + "\n" + blk.text).strip()
                target.has_table = True
            elif blk.kind == "image" and blk.figure is not None:
                target.figures.append(blk.figure)

    # drop empty sections (heading with no content) but keep for hierarchy if needed
    return sections
