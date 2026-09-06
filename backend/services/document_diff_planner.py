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


def _sanitize_table_against_hallucination(
    reference_content: str, new_table_markdown: str, device_excerpts_text: str
) -> tuple[str, int]:
    """Revert any changed table cell whose new value doesn't literally
    appear anywhere in the device excerpts.

    Prompt wording alone ("never infer/guess") is not a reliable enough
    guardrail: models will still pattern-complete a plausible-looking
    value for an empty cell even when explicitly told not to (seen in
    practice - empty "Indicator Light" cells filled in by inferring a
    color from the row's priority level, with nothing in either document
    actually stating that color, even after the prompt was tightened). For
    a medical-device document, an unverifiable fabricated value is worse
    than a missed real one, so this check is mechanical, not another LLM
    instruction to hope is followed.

    Returns (sanitized_markdown, reverted_cell_count). If the table shapes
    don't line up (row/column count mismatch - the model restructured the
    table instead of just editing values in place), returns the new table
    unchanged; that's a case that still needs human review, not something
    this cell-level check can safely correct on its own.
    """
    orig_rows = _extract_markdown_table(reference_content)
    new_rows = _extract_markdown_table(new_table_markdown)
    if orig_rows is None or new_rows is None:
        return new_table_markdown, 0
    if len(orig_rows) != len(new_rows) or any(
        len(r1) != len(r2) for r1, r2 in zip(orig_rows, new_rows)
    ):
        return new_table_markdown, 0

    device_lower = device_excerpts_text.lower()
    reverted = 0
    sanitized_rows: list[list[str]] = []
    for orig_row, new_row in zip(orig_rows, new_rows):
        out_row = []
        for orig_cell, new_cell in zip(orig_row, new_row):
            if new_cell != orig_cell and new_cell and new_cell.lower() not in device_lower:
                out_row.append(orig_cell)
                reverted += 1
            else:
                out_row.append(new_cell)
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
        device_excerpts_text = _format_device_excerpts(matches)
        new_table_markdown, reverted = _sanitize_table_against_hallucination(
            section.content, new_table_markdown, device_excerpts_text
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
