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

_PROMPT_TEMPLATE = """You are helping generate a device-specific technical document from a fixed company reference template. The reference document's structure, headings, and wording must NOT change - only device-specific facts, numbers, and table values may be updated, and only when the device document actually provides a specific value for something the reference states generically or with a different device's data.

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

"new_paragraphs", if not null, must be the FULL replacement text for the section's paragraphs (same number of paragraphs as the reference, same general wording), with only the device-specific values swapped in - not a diff, not a summary. "new_table_markdown", if not null, must be the FULL replacement Markdown table (same row/column structure as the reference's table, header included) with only cell values updated - only set this if the reference section actually contains a table."""


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

    return SectionPlan(
        section_id=section.id,
        section_name=section.section_name,
        changed=bool(parsed.get("changed", False)),
        reason=parsed.get("reason", ""),
        new_paragraphs=parsed.get("new_paragraphs"),
        new_table_markdown=parsed.get("new_table_markdown"),
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
