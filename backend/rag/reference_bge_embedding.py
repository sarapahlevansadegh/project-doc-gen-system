"""Phase 4: cross-corpus matching between reference-document sections and
device-document chunks.

Both are embedded with bge-base-en-v1.5 (see rag/embeddings.py and
rag/device_embedding_service.py), so document_templates.embedding and
document_chunks.embedding live in the same vector space and can be
compared directly - no separate embedding step needed here, a reference
section already has its embedding populated at upload time by
rag/retriever.py's store_sections().
"""
from __future__ import annotations

import uuid

from models.template import DocumentTemplate
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def find_matching_device_chunks(
    db: AsyncSession,
    reference_section_id: uuid.UUID,
    device_document_id: uuid.UUID,
    k: int = 5,
) -> list[dict]:
    """For one reference section, find its k most similar chunks within a
    specific device document, via cosine distance in the shared bge-base
    vector space. Returns [] if the reference section has no embedding yet
    (shouldn't normally happen - store_sections() embeds on upload).

    Scoped to a single device_document_id rather than searching across all
    device documents - the Phase 4 workflow always compares one reference
    document against one specific device document at a time, not against
    every device document ever uploaded.
    """
    ref_row = await db.get(DocumentTemplate, reference_section_id)
    if ref_row is None or ref_row.embedding is None:
        return []

    embedding_str = f"[{','.join(map(str, ref_row.embedding))}]"
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
