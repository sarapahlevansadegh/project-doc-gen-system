"""Phase 5: apply an approved section-level plan to the actual reference
.docx and produce the final device-specific document.

Deliberately re-plans each section from its full, unsplit text (via
rag/extractor.py's LiveSection) rather than reusing services/
document_diff_planner.py's already-computed /plan preview: that preview is
built from rag/splitter.py's max_chars-split rows, which can slice one
heading section into several overlapping "(part N)" pieces with no clean
mapping back to specific paragraphs/table cells to edit. See LiveSection's
docstring in rag/extractor.py for the full reasoning. This module reuses
build_section_plan() itself (same prompt, same matching, same table
guardrail already tested in test_document_diff_planner.py) - only the
section granularity fed into it differs from the /plan endpoint's.

Formatting note: only paragraph.text and cell.text are changed. python-docx
collapses a paragraph to a single run in the paragraph's own default style
when text is set this way, so run-level formatting mid-paragraph (e.g. one
bolded word inside an otherwise-plain sentence) is not preserved -
paragraph-level style, and all table/cell formatting, is untouched.
Figures/images are copied through untouched; this module only ever
addresses text and tables, matching document_diff_planner's own scope.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from agent.llm import LLMClient, get_llm_client
from config import settings
from docx.table import Table
from docx.text.paragraph import Paragraph
from models.device_document import DeviceDocument
from models.template import ReferenceDocument
from rag.embeddings import embed_text
from rag.extractor import LiveSection, extract_docx_live
from services.device_document_service import _sanitize_filename
from services.document_diff_planner import build_section_plan
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict], Awaitable[None]]


class _SyntheticSection:
    """Duck-typed stand-in for a DocumentTemplate row, holding a
    LiveSection's full unsplit text - never persisted to document_templates.
    build_section_plan() only ever reads .id/.section_name/.content/
    .embedding off what it's given, so this is a safe substitute; see that
    function's docstring.
    """

    def __init__(self, section_name: str, content: str, embedding: list[float]):
        self.id = uuid.uuid4()
        self.section_name = section_name
        self.content = content
        self.embedding = embedding


def _apply_paragraphs(paragraphs: list[Paragraph], new_texts: list[str]) -> None:
    """Replace paragraph text in place, one new_texts entry per existing
    paragraph, in order.

    If the model returned more paragraphs than the reference has, the
    extra text is appended onto the last paragraph rather than dropped.
    If it returned fewer, the remaining original paragraphs are left as-is
    rather than blanked out - losing reference wording outright would be
    worse than one paragraph occasionally not receiving an update.
    """
    n = min(len(paragraphs), len(new_texts))
    for i in range(n):
        paragraphs[i].text = new_texts[i]
    if len(new_texts) > len(paragraphs) and paragraphs:
        extra = " ".join(new_texts[len(paragraphs):])
        paragraphs[-1].text = f"{paragraphs[-1].text} {extra}".strip()


def _parse_markdown_table(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.strip().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r"-{3,}", c) for c in cells):
            continue  # markdown header-separator row
        rows.append(cells)
    return rows


def _apply_table(table: Table, new_table_markdown: str) -> None:
    """Write new cell text into the existing live Table, cell by cell,
    matched by row/column index - only when the parsed replacement's shape
    matches the existing table exactly. A shape mismatch means the model
    restructured the table rather than updating values in place, which
    can't be safely applied cell-by-cell; the table is left untouched
    rather than guessing at a re-layout (same conservative rule
    document_diff_planner's own guardrail already applies at plan time).
    """
    new_rows = _parse_markdown_table(new_table_markdown)
    existing_rows = table.rows
    if len(new_rows) != len(existing_rows):
        logger.warning(
            "Table row count mismatch (existing=%d, new=%d) - leaving table unchanged",
            len(existing_rows), len(new_rows),
        )
        return
    for row_idx, row in enumerate(existing_rows):
        if len(row.cells) != len(new_rows[row_idx]):
            logger.warning(
                "Table column count mismatch on row %d - leaving table unchanged",
                row_idx,
            )
            return
    for row_idx, row in enumerate(existing_rows):
        for col_idx, cell in enumerate(row.cells):
            new_value = new_rows[row_idx][col_idx]
            if cell.text.strip() != new_value:
                cell.text = new_value


async def _plan_and_apply_section(
    db: AsyncSession,
    section: LiveSection,
    device_document_id: uuid.UUID,
    llm: LLMClient,
) -> tuple[bool, str]:
    """Re-plan one LiveSection from its full text and apply the result
    directly onto its live paragraph/table objects. Returns (changed, reason).
    """
    section_text = section.text
    if not section_text:
        return False, "Section has no content to compare"

    embedding = await embed_text(section_text)
    synthetic = _SyntheticSection(section.title, section_text, embedding)
    plan = await build_section_plan(db, synthetic, device_document_id, llm)

    if not plan.changed:
        return False, plan.reason

    paragraphs = [b for b in section.blocks if isinstance(b, Paragraph)]
    tables = [b for b in section.blocks if isinstance(b, Table)]

    if plan.new_paragraphs and paragraphs:
        _apply_paragraphs(paragraphs, plan.new_paragraphs)
    if plan.new_table_markdown and tables:
        # A section rarely has more than one table; if it does, the same
        # replacement markdown is applied to each - build_section_plan's
        # prompt only ever describes "the section's table" singular, so a
        # multi-table section isn't something the current prompt/response
        # shape can address per-table anyway.
        for table in tables:
            _apply_table(table, plan.new_table_markdown)

    return True, plan.reason


async def generate_final_document(
    db: AsyncSession,
    reference_doc: ReferenceDocument,
    device_document_id: uuid.UUID,
    output_dir: Path | str | None = None,
    llm: LLMClient | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """Open reference_doc's actual .docx, re-plan and apply changes section
    by section, and save a new file - the original reference file on disk
    is never modified. Returns {"output_path": Path, "sections": {name: reason}}.
    """
    if not reference_doc.storage_path:
        raise ValueError(f"Reference document {reference_doc.id} has no storage_path")

    llm = llm or get_llm_client()
    output_dir = Path(output_dir) if output_dir else Path(settings.generated_docs_path)

    document, live_sections = extract_docx_live(reference_doc.storage_path)

    sections_result: dict[str, str] = {}
    total = len(live_sections) or 1
    for index, section in enumerate(live_sections):
        if progress_callback:
            await progress_callback(
                {
                    "status": "processing",
                    "section": section.title,
                    "progress": int(index / total * 100),
                    "message": f"Evaluating section: {section.title}",
                }
            )

        changed, reason = await _plan_and_apply_section(
            db, section, device_document_id, llm
        )
        sections_result[section.heading_path] = reason

        if progress_callback:
            await progress_callback(
                {
                    "status": "processing",
                    "section": section.title,
                    "progress": int((index + 1) / total * 100),
                    "message": (
                        f"Updated section: {section.title}"
                        if changed
                        else f"No change needed: {section.title}"
                    ),
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_base = _sanitize_filename(reference_doc.template_name) or "document"
    output_path = output_dir / f"{safe_base}_generated_{uuid.uuid4().hex[:8]}.docx"
    document.save(str(output_path))
    logger.info(
        "Generated final document %s (%d sections evaluated)",
        output_path, len(live_sections),
    )
    return {"output_path": output_path, "sections": sections_result}


async def generate_document_for_job(
    db: AsyncSession,
    device_id: uuid.UUID | str,
    reference_doc_id: uuid.UUID | str,
    llm: LLMClient | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """services/generation_service.py's entry point: resolve the device's
    most recently uploaded document and the reference document row, then
    delegate to generate_final_document(). Kept separate from that
    function so it stays callable directly (e.g. from a script or test)
    without needing a device_id at all - only a device_document_id.
    """
    device_id = uuid.UUID(str(device_id))
    reference_doc_id = uuid.UUID(str(reference_doc_id))

    reference_doc = await db.get(ReferenceDocument, reference_doc_id)
    if reference_doc is None:
        raise ValueError(f"Reference document {reference_doc_id} not found")

    result = await db.execute(
        select(DeviceDocument)
        .where(DeviceDocument.device_id == device_id)
        .order_by(DeviceDocument.created_at.desc())
        .limit(1)
    )
    device_document = result.scalar_one_or_none()
    if device_document is None:
        raise ValueError(f"Device {device_id} has no uploaded document to generate from")

    return await generate_final_document(
        db,
        reference_doc,
        device_document.id,
        llm=llm,
        progress_callback=progress_callback,
    )
