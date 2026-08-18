"""Heading-aware section splitter.

Turns extracted outline sections into RAG sections. Blind character chunking
is avoided: each heading-bounded section becomes one unit. Only when a single
section exceeds ``max_chars`` do we fall back to a recursive split that is
scoped *within* that section and preserves its name/level.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter
from models.template import SectionType as DbSectionType

from rag.extractor import ExtractedSection


@dataclass
class RagSection:
    section_name: str
    heading_level: int
    parent_section: str | None
    content: str
    section_type: str
    figure_refs: list[dict]
    order: int


# Heuristics for inferring a section's type from its title/content.
_TYPE_RULES = [
    (DbSectionType.ALARM, re.compile(r"\b(alarm|warning|error display)\b", re.I)),
    (DbSectionType.INTERFACE, re.compile(r"\b(interface|serial communication|rs-232)\b", re.I)),
    (DbSectionType.REQUIREMENT, re.compile(r"\b(requirement|soup|functional|performance)\b", re.I)),
    (DbSectionType.FIGURE, re.compile(r"\b(figure|diagram)\b", re.I)),
    (DbSectionType.TABLE, re.compile(r"\b(table|specifications)\b", re.I)),
]


def _infer_type(section: ExtractedSection) -> str:
    # Type is a structural property of the section heading, not its prose,
    # so we match against the title only (avoids false positives from body
    # text like "Figure 1" or "warning" appearing in paragraphs).
    haystack = section.title
    for stype, pattern in _TYPE_RULES:
        if pattern.search(haystack):
            return stype.value
    if section.figures:
        return DbSectionType.FIGURE.value
    if section.has_table:
        return DbSectionType.TABLE.value
    return DbSectionType.TEXT.value


def split_sections(
    sections: list[ExtractedSection],
    max_chars: int = 2500,
) -> list[RagSection]:
    """Convert outline sections into RAG sections (no blind chunking)."""
    out: list[RagSection] = []
    order = 0

    # intra-section fallback splitter (only used when a section is huge)
    fallback = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " "],
    )

    for sec in sections:
        parent = None
        if ">" in sec.heading_path:
            parent = sec.heading_path.rsplit(" > ", 1)[0]

        stype = _infer_type(sec)

        if len(sec.body) <= max_chars:
            order += 1
            out.append(
                RagSection(
                    section_name=sec.title or sec.heading_path,
                    heading_level=sec.level,
                    parent_section=parent,
                    content=sec.body,
                    section_type=stype,
                    figure_refs=sec.figure_refs,
                    order=order,
                )
            )
            continue

        # huge section: split within, keep name/level/type, mark sub-order
        chunks = fallback.split_text(sec.body)
        for i, chunk in enumerate(chunks, start=1):
            order += 1
            name = sec.title if i == 1 else f"{sec.title} (part {i})"
            out.append(
                RagSection(
                    section_name=name,
                    heading_level=sec.level,
                    parent_section=parent,
                    content=chunk,
                    section_type=stype,
                    figure_refs=sec.figure_refs if i == 1 else [],
                    order=order,
                )
            )

    return out
