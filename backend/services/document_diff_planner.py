"""Phase 4: decide what, if anything, should change in each reference
section based on the matched device-document content.

Produces a structured plan only - this module never touches the actual
reference .docx. Applying an approved plan to a real document is a
separate step (services/document_generator.py), kept separate so the
plan's quality can be reviewed before any file gets written.

Core rule (confirmed before implementation): the reference document's
structure, headings, and wording must never change. Only device-specific
facts/numbers/table values may be swapped in, and only where the device
document actually provides something specific for a spot the reference
states generically (or with a different device's data). A section with no
sufficiently similar device-document content is left unchanged rather than
guessed at.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from agent.llm import LLMClient, get_llm_client
from models.template import DocumentTemplate
from rag.reference_bge_embedding import find_matching_device_chunks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Below this cosine similarity, treat the top match as "not actually about
# this section" and leave the section unchanged rather than let the LLM
# guess from a weak/irrelevant match.
DEFAULT_SIMILARITY_THRESHOLD = 0.5

_PROMPT_TEMPLATE = """You are helping generate a device-specific technical document from a fixed company reference template. The reference document's structure, headings, and wording must NOT change - only device-specific facts, numbers, and table values may be updated, and only when the device document actually provides a different/specific value for something the reference states generically or with a different device's data.

CRITICAL: Only replace a value when the device document excerpts literally state that specific value. Never infer, calculate, or guess a replacement value (e.g. do not fill an empty cell by pattern-matching other rows, do not assume a color/label/number because it "seems right" for that category). An empty or generic cell/field that the device document doesn't explicitly address must be copied through UNCHANGED, exactly as it appears in the reference - never leave it as-is by omission and never quietly fill it in.

REFERENCE SECTION (do not change wording/structure unless a specific fact must be updated):
---
{reference_text}
---

CANDIDATE DEVICE-DOCUMENT EXCERPTS (most relevant first, with similarity scores):
---
{device_excerpts}
---

Decide: does the device document provide specific facts that should replace anything in the reference section above? If the reference section is generic boilerplate with nothing device-specific in it, or the device excerpts don't actually address this section's topic, respond with no changes.

Respond with ONLY a JSON object, no markdown code fences, no commentary before or after:
{{
  "changed": true or false,
  "reason": "one short sentence explaining the decision",
  "new_paragraphs": ["paragraph one", "paragraph two"] or null,
  "new_table_markdown": "| Col1 | Col2 |\\n| --- | --- |\\n| val | val |" or null
}}

"new_paragraphs", if not null, must be the FULL replacement text for the section's paragraphs (same number of paragraphs as the reference, same general wording), with only the device-specific values swapped in - not a diff, not a summary. "new_table_markdown", if not null, must be the FULL replacement Markdown table (same row/column structure as the reference's table, same row order, header included) with ONLY the specific cells the device document actually addresses changed - every other cell, including empty ones, copied through byte-for-byte identical to the reference table."""


@dataclass
class SectionPlan:
    section_id: uuid.UUID
    section_name: str
    changed: bool
    reason: str
    new_paragraphs: list[str] | None = None
    new_table_markdown: str | None = None
    best_similarity: float | None = None


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _format_device_excerpts(matches: list[dict]) -> str:
    if not matches:
        return "(no relevant device-document content found)"
    return "\n\n".join(
        f"[similarity {m['similarity']:.2f}]\n{m['chunk_text']}" for m in matches
    )


_TABLE_LINE_RE = re.compile(r"^\|.*\|\s*$")


def _extract_markdown_table(text: str) -> list[list[str]] | None:
    """Pull the rows of the first Markdown table found in `text` (header +
    data rows; the `| --- |` separator row is dropped). Returns None if no
    table-shaped lines are present."""
    lines = [line.strip() for line in text.split("\n") if _TABLE_LINE_RE.match(line.strip())]
    if len(lines) < 2:
        return None

    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    if len(rows) >= 2 and all(set(cell) <= {"-"} for cell in rows[1] if cell):
        rows.pop(1)
    return rows


def _rebuild_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    col_count = len(rows[0])
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * col_count) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


_MIN_ANCHOR_LEN = 4


def _sanitize_table_against_hallucination(
    reference_content: str, new_table_markdown: str, matches: list[dict]
) -> tuple[str, int]:
    """Revert any changed table cell that isn't verifiably backed by the
    device document, checked per-row rather than against the whole device
    excerpts blob at once.

    Three guardrail attempts, three real failure modes found by testing
    against the actual reference + device documents:

    1. Prompt wording alone ("never infer/guess") was not reliable: the
       model filled an empty "Indicator Light" cell with an inferred color
       pattern-matched from the row's priority level, with nothing in
       either document stating it.
    2. A flat "does the new value appear ANYWHERE in the device excerpts"
       check was too permissive: a generic value like "Color: Red" that's
       real for row 1 was accepted as "verified" for a different row,
       because the check had no notion of *which row* it was checking.
    3. Checking "does the anchor and the new value both appear in the SAME
       chunk" still wasn't precise enough: rag/chunker.py keeps a whole
       table as one atomic chunk (deliberately, to never split a table -
       see chunker.py), so when the device document contains its own
       near-identical table, that entire table (every row) is one chunk.
       The row-2 anchor and row-1's real "Color: Red" both live in that
       same chunk, so they still "co-occurred" despite being unrelated
       rows.

    Fix: when a device excerpt chunk itself contains a table, parse it and
    compare row-to-row, column-to-column - find the device table row whose
    cells contain this reference row's anchor text, then only accept a
    cell change if that SAME COLUMN of the matched device row actually
    supports it. This is what catches the row-2 case: the device
    document's own row 2 also has an empty Indicator Light cell, so
    column-aligned comparison correctly finds no support and reverts,
    where flat text search kept finding row 1's unrelated "Color: Red"
    anywhere in the chunk. Falls back to the weaker anchor+chunk
    co-occurrence check only when no device table row matches this
    reference row at all (e.g. the device document only discusses it in
    prose, not a table).

    Returns (sanitized_markdown, reverted_cell_count). If the reference
    and new table shapes don't line up (row/column count mismatch),
    returns the new table unchanged; that's a case needing human review,
    not something this cell-level check can safely correct on its own.
    """
    orig_rows = _extract_markdown_table(reference_content)
    new_rows = _extract_markdown_table(new_table_markdown)
    if orig_rows is None or new_rows is None:
        return new_table_markdown, 0
    if len(orig_rows) != len(new_rows) or any(
        len(r1) != len(r2) for r1, r2 in zip(orig_rows, new_rows)
    ):
        return new_table_markdown, 0

    device_tables = [
        t for t in (_extract_markdown_table(m["chunk_text"]) for m in matches) if t
    ]
    chunk_texts_lower = [m["chunk_text"].lower() for m in matches]

    reverted = 0
    sanitized_rows: list[list[str]] = []
    for orig_row, new_row in zip(orig_rows, new_rows):
        # the row's own anchor: its longest original cell, i.e. the most
        # specific/identifying text for *this* row (typically the
        # condition/description column) - bare numbers or "High"/"Medium"
        # aren't distinctive enough to localize a row.
        anchor = max(orig_row, key=len).strip().lower()
        anchor_ok = len(anchor) >= _MIN_ANCHOR_LEN

        matched_device_row: list[str] | None = None
        if anchor_ok:
            for device_table in device_tables:
                for device_row in device_table:
                    if any(anchor in (cell or "").lower() for cell in device_row):
                        matched_device_row = device_row
                        break
                if matched_device_row is not None:
                    break

        anchor_chunks = (
            [text for text in chunk_texts_lower if anchor in text] if anchor_ok else []
        )

        out_row = []
        for col_idx, (orig_cell, new_cell) in enumerate(zip(orig_row, new_row)):
            if new_cell == orig_cell or not new_cell:
                out_row.append(new_cell)
                continue

            new_cell_lower = new_cell.lower()
            if matched_device_row is not None:
                # precise: does this matched device row's SAME column
                # actually contain the proposed value? A matched row
                # takes priority over the looser chunk-text fallback below
                # even when it doesn't support the change - the device
                # document does discuss this row, and if its own value
                # disagrees (or is blank), that's stronger evidence than a
                # coincidental text match elsewhere.
                device_cell = (
                    device_row_cell.lower()
                    if col_idx < len(matched_device_row)
                    and (device_row_cell := matched_device_row[col_idx])
                    else ""
                )
                verified = bool(device_cell) and new_cell_lower in device_cell
            else:
                verified = any(new_cell_lower in chunk for chunk in anchor_chunks)

            if verified:
                out_row.append(new_cell)
            else:
                out_row.append(orig_cell)
                reverted += 1
        sanitized_rows.append(out_row)

    return _rebuild_markdown_table(sanitized_rows), reverted


async def build_section_plan(
    db: AsyncSession,
    section: DocumentTemplate,
    device_document_id: uuid.UUID,
    llm: LLMClient,
    k: int = 5,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> SectionPlan:
    if not section.content or not section.content.strip():
        return SectionPlan(
            section_id=section.id,
            section_name=section.section_name,
            changed=False,
            reason="Section has no content to compare",
        )

    matches = await find_matching_device_chunks(db, section.id, device_document_id, k=k)
    best_similarity = matches[0]["similarity"] if matches else None

    if not matches or best_similarity < similarity_threshold:
        return SectionPlan(
            section_id=section.id,
            section_name=section.section_name,
            changed=False,
            reason="No sufficiently similar device-document content found",
            best_similarity=best_similarity,
        )

    prompt = _PROMPT_TEMPLATE.format(
        reference_text=section.content,
        device_excerpts=_format_device_excerpts(matches),
    )
    raw = llm.generate(prompt, max_tokens=2000, temperature=0.2)

    try:
        parsed = json.loads(_strip_json_fences(raw))
    except (json.JSONDecodeError, TypeError):
        return SectionPlan(
            section_id=section.id,
            section_name=section.section_name,
            changed=False,
            reason=f"Could not parse LLM response as JSON: {raw[:200]!r}",
            best_similarity=best_similarity,
        )

    reason = parsed.get("reason", "")
    new_table_markdown = parsed.get("new_table_markdown")
    if new_table_markdown:
        new_table_markdown, reverted = _sanitize_table_against_hallucination(
            section.content, new_table_markdown, matches
        )
        if reverted:
            reason += (
                f" [{reverted} table cell(s) reverted to the reference value - "
                "the model's replacement wasn't traceable to the device document]"
            )

    return SectionPlan(
        section_id=section.id,
        section_name=section.section_name,
        changed=bool(parsed.get("changed", False)),
        reason=reason,
        new_paragraphs=parsed.get("new_paragraphs"),
        new_table_markdown=new_table_markdown,
        best_similarity=best_similarity,
    )


async def build_document_plan(
    db: AsyncSession,
    reference_id: uuid.UUID,
    device_document_id: uuid.UUID,
    llm: LLMClient | None = None,
    k: int = 5,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[SectionPlan]:
    """Build a change plan for every section of one reference document
    against one device document, in section order."""
    result = await db.execute(
        select(DocumentTemplate)
        .where(DocumentTemplate.source_doc_id == reference_id)
        .order_by(DocumentTemplate.section_order)
    )
    sections = result.scalars().all()
    llm = llm or get_llm_client()

    plans = []
    for section in sections:
        plan = await build_section_plan(
            db, section, device_document_id, llm, k=k, similarity_threshold=similarity_threshold
        )
        plans.append(plan)
    return plans
