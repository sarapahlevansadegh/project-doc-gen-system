"""Parse an uploaded Device DOCX into structured sections (Phase 2.5).

Reuses the same extraction/splitting pipeline already built for reference
documents (``rag.extractor.extract_docx`` + ``rag.splitter.split_sections``)
so headings, paragraphs, tables, and figure references are captured the same
way on both sides - a prerequisite for the Phase 4 agent to later compare
a device's own document against the reference template.

Only ``.docx`` can be parsed this way (python-docx cannot read ``.pdf`` or
legacy ``.doc``). For those, parsing is skipped rather than failing the
upload; Phase 2.5's Vision pipeline is the planned way to cover them later.
"""
from __future__ import annotations

import logging
from pathlib import Path

from models.device_document import DeviceDocumentSection
from rag import image_extractor
from rag.extractor import extract_docx
from rag.image_captioner import caption_image, captioning_enabled
from rag.splitter import split_sections
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PARSEABLE_EXTENSIONS = {".docx"}

_SECTION_NAME_MAX = 255


def _truncate(text: str | None, max_len: int) -> str | None:
    """Defensively cap a value at the DB column limit.

    Reference/device headings occasionally come out longer than a normal
    heading (a mis-detected paragraph, an unusually long title) - truncate
    rather than let the whole upload fail on one oversized row.
    """
    if text is None:
        return None
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


async def parse_and_store_sections(
    db: AsyncSession,
    document_id,
    storage_path: str,
) -> int:
    """Extract structure from a Device DOCX and persist it. Returns the
    number of sections stored (0 if the file type isn't parseable, or if
    extraction failed - a bad/corrupt device file should not block the
    upload itself)."""
    suffix = Path(storage_path).suffix.lower()
    if suffix not in PARSEABLE_EXTENSIONS:
        logger.info(
            "Skipping structural parse for device document %s: unsupported extension %s",
            document_id,
            suffix,
        )
        return 0

    try:
        extracted = extract_docx(storage_path)
        rag_sections = split_sections(extracted)
    except Exception:
        logger.exception(
            "Failed to parse device document %s at %s", document_id, storage_path
        )
        return 0

    # Pull the real image bytes out of the docx zip for every figure
    # referenced anywhere in the document (Phase 2.5, Part B), in one pass -
    # sections only ever carried a rel_id pointer to the image before this.
    all_rel_ids = {
        fig["rel_id"]
        for sec in rag_sections
        for fig in sec.figure_refs
        if fig.get("rel_id")
    }
    saved_images = image_extractor.extract_images(
        storage_path, document_id=document_id, rel_ids=all_rel_ids
    )

    count = 0
    for sec in rag_sections:
        figure_refs = [
            {**fig, "image_path": saved_images[fig["rel_id"]]}
            if fig.get("rel_id") in saved_images
            else fig
            for fig in sec.figure_refs
        ]

        # Optional Vision LLM captioning (Phase 3, item 2). Off by default;
        # a caption failure never blocks parsing/storage of the section -
        # caption_image() is fail-soft and returns None on any problem.
        # The caption is appended to `content` (so it becomes searchable
        # text for embedding) and also kept per-image in figure_refs (so the
        # UI can show it next to the figure); the image itself is untouched.
        content = sec.content
        if captioning_enabled():
            captions: list[str] = []
            for fig in figure_refs:
                image_path = fig.get("image_path")
                if not image_path:
                    continue
                caption = caption_image(image_path)
                if caption:
                    fig["caption"] = caption
                    captions.append(caption)
            if captions:
                content = (content + "\n\n" + "\n".join(captions)).strip()

        db.add(
            DeviceDocumentSection(
                document_id=document_id,
                section_name=_truncate(sec.section_name, _SECTION_NAME_MAX) or "",
                section_type=sec.section_type,
                heading_level=sec.heading_level,
                parent_section=_truncate(sec.parent_section, _SECTION_NAME_MAX),
                section_order=sec.order,
                content=content,
                figure_refs=figure_refs,
            )
        )
        count += 1

    try:
        await db.commit()
    except Exception:
        # A row-level DB error (e.g. an unexpected constraint) must not take
        # the whole upload down - roll back so the session is usable again
        # and the caller's own commit (the DeviceDocument row, already
        # saved) is unaffected.
        await db.rollback()
        logger.exception(
            "Failed to store parsed sections for device document %s", document_id
        )
        return 0

    logger.info(
        "Parsed device document %s: %d sections stored", document_id, count
    )
    return count
