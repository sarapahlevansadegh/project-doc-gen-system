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

import hashlib
import logging
import os
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
from rag.extractor import LiveSection, _iter_block_items, extract_docx_live
from services.device_document_service import _sanitize_filename
from services.document_diff_planner import build_section_plan
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Debugging aid for the paragraph-duplication investigation (read-only
# instrumentation - no behavior change). Off by default: only short
# previews are logged. Set DOCGEN_DEBUG_DUPLICATION_LOG=1 to log full
# paragraph text, per the requirement that full document text is only
# captured in a controlled debug run, never by default.
_DEBUG_FULL_TEXT = os.environ.get("DOCGEN_DEBUG_DUPLICATION_LOG") == "1"


def _block_xml_key(block: Paragraph | Table) -> int:
    """Stable-within-one-run identity for a python-docx block, keyed off
    the underlying XML element rather than the wrapper object's id() -
    python-docx creates a fresh Paragraph/Table wrapper on every access,
    so two separate traversals never share wrapper identity even though
    they refer to the same document position. This key is only ever used
    as an in-process lookup; logged locators are the stable integer
    positions in ``block_locator`` below, not this key itself."""
    return id(block._p) if isinstance(block, Paragraph) else id(block._tbl)


def _build_block_locator(document) -> dict[int, int]:
    """Maps each block's _block_xml_key() to its stable, reproducible
    position among all top-level blocks in the document (paragraphs and
    tables, in document order). Computed once per run and threaded
    through for logging only - never persisted, never affects which
    paragraph/cell actually gets written."""
    return {
        _block_xml_key(block): index
        for index, block in enumerate(_iter_block_items(document))
    }


def _code_version() -> str:
    """Best-effort git commit SHA of the code currently running, so a log
    line can be compared against a previous run's log to tell whether the
    generation logic itself changed between them. Falls back to
    "unknown" rather than failing - git may not be installed/available in
    the running container."""
    try:
        import subprocess

        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, timeout=2
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"

ProgressCallback = Callable[[dict], Awaitable[None]]


def _sha256_file(path: str | Path) -> str:
    """Hex digest of a file's exact bytes on disk, used to pin a generated
    job's result to the precise reference/device-document content it was
    built from (see generate_document_for_job)."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _apply_paragraphs(
    paragraphs: list[Paragraph],
    new_texts: list[str],
    *,
    run_id: str | None = None,
    section_heading: str | None = None,
    locator: dict[int, int] | None = None,
) -> None:
    """Replace paragraph text in place, one new_texts entry per existing
    paragraph, in order.

    If the model returned more paragraphs than the reference has, the
    extra text is appended onto the last paragraph rather than dropped.
    If it returned fewer, the remaining original paragraphs are left as-is
    rather than blanked out - losing reference wording outright would be
    worse than one paragraph occasionally not receiving an update.
    """
    if run_id is not None:
        # Duplication-investigation logging (read-only instrumentation):
        # the target list this call is about to zip new_texts against,
        # with each target's stable document-position locator, so a run's
        # log can be checked for offset/misalignment after the fact.
        for i, p in enumerate(paragraphs):
            gidx = locator.get(_block_xml_key(p), -1) if locator else -1
            preview = p.text if _DEBUG_FULL_TEXT else f"{p.text[:40]!r} ({len(p.text)} chars)"
            logger.info(
                "run=%s section=%r apply_target[%d] block=%d empty=%s text=%s",
                run_id, section_heading, i, gidx, not p.text.strip(), preview,
            )
        logger.info(
            "run=%s section=%r apply_paragraphs: targets=%d new_texts=%d",
            run_id, section_heading, len(paragraphs), len(new_texts),
        )

    n = min(len(paragraphs), len(new_texts))
    for i in range(n):
        if run_id is not None:
            gidx = locator.get(_block_xml_key(paragraphs[i]), -1) if locator else -1
            new_preview = new_texts[i] if _DEBUG_FULL_TEXT else f"{new_texts[i][:40]!r} ({len(new_texts[i])} chars)"
            logger.info(
                "run=%s section=%r overwrite block=%d (target_idx=%d) <- new_texts[%d]=%s",
                run_id, section_heading, gidx, i, i, new_preview,
            )
        paragraphs[i].text = new_texts[i]
    if len(new_texts) > len(paragraphs) and paragraphs:
        extra = " ".join(new_texts[len(paragraphs):])
        if run_id is not None:
            logger.info(
                "run=%s section=%r extra new_texts[%d:%d] (%d items) appended onto last target",
                run_id, section_heading, len(paragraphs), len(new_texts), len(new_texts) - len(paragraphs),
            )
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
    *,
    run_id: str | None = None,
    locator: dict[int, int] | None = None,
) -> tuple[bool, str]:
    """Re-plan one LiveSection from its full text and apply the result
    directly onto its live paragraph/table objects. Returns (changed, reason).
    """
    section_text = section.text
    if not section_text:
        return False, "Section has no content to compare"

    embedding = await embed_text(section_text)
    synthetic = _SyntheticSection(section.title, section_text, embedding)
    plan = await build_section_plan(
        db, synthetic, device_document_id, llm, run_id=run_id
    )

    if not plan.changed:
        return False, plan.reason

    paragraphs = [b for b in section.blocks if isinstance(b, Paragraph)]
    tables = [b for b in section.blocks if isinstance(b, Table)]

    if run_id is not None:
        logger.info(
            "run=%s section=%r plan.new_paragraphs=%s plan.new_table_markdown=%s "
            "true_paragraph_targets=%d true_table_targets=%d",
            run_id, section.heading_path,
            len(plan.new_paragraphs) if plan.new_paragraphs else None,
            "present" if plan.new_table_markdown else None,
            len(paragraphs), len(tables),
        )

    reason = plan.reason
    # One new text per existing paragraph, in order: a different count means
    # the model's paragraphs don't line up with this section, and zipping
    # them anyway would overwrite the wrong paragraphs or merge text onto
    # the last one. Leave the paragraphs as they are and flag the section.
    paragraph_mismatch = bool(
        plan.new_paragraphs and paragraphs and len(plan.new_paragraphs) != len(paragraphs)
    )
    if paragraph_mismatch:
        reason += (
            f" [needs_review - the model returned {len(plan.new_paragraphs)} "
            f"paragraph(s) for a section with {len(paragraphs)}; paragraphs "
            "left unchanged]"
        )
    elif plan.new_paragraphs and paragraphs:
        _apply_paragraphs(
            paragraphs, plan.new_paragraphs,
            run_id=run_id, section_heading=section.heading_path, locator=locator,
        )
    tables_applied = False
    if plan.new_table_markdown and tables:
        # A section rarely has more than one table; if it does, the same
        # replacement markdown is applied to each - build_section_plan's
        # prompt only ever describes "the section's table" singular, so a
        # multi-table section isn't something the current prompt/response
        # shape can address per-table anyway.
        for table in tables:
            _apply_table(table, plan.new_table_markdown)
        tables_applied = True

    if paragraph_mismatch and not tables_applied:
        return False, reason
    return True, reason


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

    # Duplication-investigation instrumentation (read-only: logging only,
    # no behavior change). run_id correlates every log line from this one
    # execution; enable with DOCGEN_DEBUG_DUPLICATION_LOG=1 for full text.
    run_id = uuid.uuid4().hex[:10]
    locator = _build_block_locator(document)
    logger.info(
        "run=%s START code_version=%s reference_doc_id=%s reference_hash=%s "
        "device_document_id=%s llm_provider=%s llm_model=%s sections=%d "
        "debug_full_text=%s",
        run_id, _code_version(), reference_doc.id,
        _sha256_file(reference_doc.storage_path), device_document_id,
        llm.provider, llm.model, len(live_sections), _DEBUG_FULL_TEXT,
    )

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
            db, section, device_document_id, llm, run_id=run_id, locator=locator
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
    logger.info("run=%s END output_path=%s", run_id, output_path)
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
    device_document_id: uuid.UUID | str,
    llm: LLMClient | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """services/generation_service.py's entry point: load the exact
    reference and device-document rows the caller pinned this job to, then
    delegate to generate_final_document(). ``device_document_id`` is
    required and validated against ``device_id`` here - no implicit
    "most recently uploaded" resolution: see db/migrations/versions/
    0012_generation_job_device_document.py for why that was unsafe (a
    newer upload arriving between job creation and execution could
    silently redirect generation to the wrong file).
    """
    device_id = uuid.UUID(str(device_id))
    reference_doc_id = uuid.UUID(str(reference_doc_id))
    device_document_id = uuid.UUID(str(device_document_id))

    reference_doc = await db.get(ReferenceDocument, reference_doc_id)
    if reference_doc is None:
        raise ValueError(f"Reference document {reference_doc_id} not found")

    device_document = await db.get(DeviceDocument, device_document_id)
    if device_document is None or device_document.device_id != device_id:
        raise ValueError(
            f"Device document {device_document_id} not found for device {device_id}"
        )

    result = await generate_final_document(
        db,
        reference_doc,
        device_document.id,
        llm=llm,
        progress_callback=progress_callback,
    )
    result["device_document_hash"] = _sha256_file(device_document.storage_path)
    result["reference_doc_hash"] = _sha256_file(reference_doc.storage_path)
    return result
