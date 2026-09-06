"""Phase 4 prerequisite: put reference-document sections and device-document
chunks in the same vector space so an agent can match them.

document_templates.embedding (MiniLM-L6-v2, 384-dim) stays exactly as-is and
keeps serving rag/retriever.py's existing within-reference-corpus retrieval.
This module only adds and uses the separate bge_embedding column (see
migration 0009_reference_bge_embedding) for reference<->device matching.
"""
from __future__ import annotations

import uuid

from models.template import DocumentTemplate
from rag.device_embedding_service import get_device_embedding_service
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


def _bge_text(row: DocumentTemplate) -> str:
    """Same breadcrumb shape as rag/chunker.py's chunk text, so a reference
    section and a device chunk that describe the same topic end up close in
    the shared embedding space for the same reason (heading context +
    body), not by coincidence."""
    breadcrumb = (
        f"{row.parent_section} > {row.section_name}" if row.parent_section else row.section_name
    )
    return f"{breadcrumb}\n\n{row.content}" if row.content else breadcrumb


async def generate_bge_embeddings(
    db: AsyncSession, reference_doc_id: uuid.UUID
) -> int:
    """(Re)compute bge-base-en-v1.5 embeddings for one reference document's
    sections. Idempotent - overwrites bge_embedding on each row every call,
    so it's safe to re-run after a re-upload or an embedding-text change."""
    result = await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.source_doc_id == reference_doc_id)
    )
    rows = result.scalars().all()
    if not rows:
        return 0

    texts = [_bge_text(row) for row in rows]
    embeddings = get_device_embedding_service().embed_documents(texts)

    for row, embedding in zip(rows, embeddings, strict=True):
        row.bge_embedding = embedding

    await db.commit()
    return len(rows)


async def find_matching_device_chunks(
    db: AsyncSession,
    reference_section_id: uuid.UUID,
    device_document_id: uuid.UUID,
    k: int = 5,
) -> list[dict]:
    """For one reference section, find its k most similar chunks within a
    specific device document, via cosine distance in the shared bge-base
    vector space. Returns [] if the reference section has no bge_embedding
    yet (call generate_bge_embeddings() first).

    Scoped to a single device_document_id rather than searching across all
    device documents - the Phase 4 workflow always compares one reference
    document against one specific device document at a time, not against
    every device document ever uploaded.
    """
    ref_row = await db.get(DocumentTemplate, reference_section_id)
    if ref_row is None or ref_row.bge_embedding is None:
        return []

    embedding_str = f"[{','.join(map(str, ref_row.bge_embedding))}]"
    sql = text(
        """
        SELECT id, chunk_text, chunk_index, figure_refs,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM document_chunks
        WHERE device_document_id = :device_document_id
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :k
        """
    )
    result = await db.execute(
        sql,
        {
            "embedding": embedding_str,
            "device_document_id": str(device_document_id),
            "k": k,
        },
    )
    return [
        {
            "chunk_id": row.id,
            "chunk_text": row.chunk_text,
            "chunk_index": row.chunk_index,
            "figure_refs": row.figure_refs,
            "similarity": row.similarity,
        }
        for row in result.fetchall()
    ]
