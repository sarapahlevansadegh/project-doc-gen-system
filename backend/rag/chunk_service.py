"""Phase 3: generate and store document_chunks for one device document.

Orchestrates rag/chunker.py (token-aware, table-safe splitting) and
rag/device_embedding_service.py (bge-base-en-v1.5 embedding) against the
device_document_sections rows already stored by Phase 2.5's
services/device_document_parser.py. Kept as its own step (not run inline
during upload) since embedding is comparatively expensive and callers may
want to re-run it independently (e.g. after a chunking logic change).
"""
from __future__ import annotations

import uuid

from models.device_document import DeviceDocumentSection
from models.document_chunk import DocumentChunk
from rag.chunker import bge_token_counter, chunk_section
from rag.device_embedding_service import get_device_embedding_service
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


async def generate_and_store_chunks(
    db: AsyncSession, device_document_id: uuid.UUID
) -> int:
    """(Re)generate all document_chunks for one device document.

    Idempotent: existing chunks for this document are deleted first, so
    re-running after a re-upload or a chunking-logic change doesn't leave
    stale rows behind (their section_id could otherwise point at content
    that no longer matches).

    Returns the number of chunks created.
    """
    result = await db.execute(
        select(DeviceDocumentSection)
        .where(DeviceDocumentSection.document_id == device_document_id)
        .order_by(DeviceDocumentSection.section_order)
    )
    sections = result.scalars().all()

    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.device_document_id == device_document_id)
    )

    token_counter = bge_token_counter()

    pending_rows: list[DocumentChunk] = []
    pending_texts: list[str] = []

    for section in sections:
        chunks = chunk_section(
            section_name=section.section_name,
            parent_section=section.parent_section,
            content=section.content,
            token_counter=token_counter,
        )
        # Every chunk from this section carries all of the section's
        # figures - the extractor already ties figures to their section as
        # a whole (not to individual paragraphs), so a finer per-chunk split
        # of figures would be precision the source data doesn't actually
        # have. Only figures that were actually extracted to disk
        # (image_path present) are worth linking; a figure_refs entry
        # without one has nothing for an agent to open.
        section_figures = [
            fig for fig in (section.figure_refs or []) if fig.get("image_path")
        ]
        for chunk in chunks:
            pending_rows.append(
                DocumentChunk(
                    section_id=section.id,
                    device_document_id=device_document_id,
                    chunk_text=chunk.text,
                    chunk_index=len(pending_rows),
                    token_count=chunk.token_count,
                    figure_refs=section_figures,
                )
            )
            pending_texts.append(chunk.text)

    if not pending_rows:
        await db.commit()
        return 0

    embedding_service = get_device_embedding_service()
    embeddings = embedding_service.embed_documents(pending_texts)
    for row, embedding in zip(pending_rows, embeddings, strict=True):
        row.embedding = embedding
        db.add(row)

    await db.commit()
    return len(pending_rows)
