"""Section-based RAG storage and retrieval."""
from __future__ import annotations

import uuid

from config import settings
from models.template import DocumentTemplate, ReferenceDocument
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.embeddings import embed_text
from rag.splitter import RagSection


async def store_sections(
    db: AsyncSession,
    reference_doc_id,
    template_name: str,
    sections: list[RagSection],
) -> int:
    """Embed and persist extracted RAG sections for a reference document."""
    count = 0
    for sec in sections:
        embedding = await embed_text(sec.content)
        row = DocumentTemplate(
            template_name=template_name,
            source_doc_id=reference_doc_id,
            section_name=sec.section_name,
            section_type=sec.section_type,
            heading_level=sec.heading_level,
            parent_section=sec.parent_section,
            section_order=sec.order,
            content=sec.content,
            figure_refs=sec.figure_refs,
            embedding=embedding,
            embedding_model=settings.embed_model,
            embedding_dimension=settings.embed_dimension,
        )
        db.add(row)
        count += 1

    ref = await db.get(ReferenceDocument, reference_doc_id)
    if ref is not None:
        ref.section_count = count

    await db.commit()
    return count


async def retrieve_similar_sections(
    db: AsyncSession,
    query: str,
    k: int = 3,
    reference_doc_id: str | None = None,
) -> list[str]:
    """Cosine similarity search over stored sections."""
    query_embedding = await embed_text(query)
    embedding_str = f"[{','.join(map(str, query_embedding))}]"

    if reference_doc_id:
        sql = text(
            """
            SELECT content, section_name,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM document_templates
            WHERE source_doc_id = :ref_id
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :k
            """
        )
        result = await db.execute(
            sql, {"embedding": embedding_str, "ref_id": reference_doc_id, "k": k}
        )
    else:
        sql = text(
            """
            SELECT content, section_name,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM document_templates
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :k
            """
        )
        result = await db.execute(sql, {"embedding": embedding_str, "k": k})

    return [row[0] for row in result.fetchall()]


async def get_reference_document(
    db: AsyncSession, reference_id: str
) -> ReferenceDocument | None:
    """Fetch a single reference document by id (None if missing/invalid)."""
    try:
        uid = uuid.UUID(reference_id)
    except ValueError:
        return None
    result = await db.execute(
        select(ReferenceDocument).where(ReferenceDocument.id == uid)
    )
    return result.scalar_one_or_none()


async def get_active_reference(
    db: AsyncSession,
) -> ReferenceDocument | None:
    """Return the currently active reference document, if any."""
    result = await db.execute(
        select(ReferenceDocument).where(ReferenceDocument.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def set_active_reference(
    db: AsyncSession, reference_id: str
) -> ReferenceDocument:
    """Mark one reference active, deactivating all others (only one active)."""
    target = await get_reference_document(db, reference_id)
    if target is None:
        return None

    others = await db.execute(
        select(ReferenceDocument).where(ReferenceDocument.is_active.is_(True))
    )
    for ref in others.scalars().all():
        if ref.id != target.id:
            ref.is_active = False
    target.is_active = True
    await db.commit()
    await db.refresh(target)
    return target


async def delete_reference(
    db: AsyncSession, reference_id: str
) -> bool:
    """Delete a reference and its stored sections/embeddings.

    Returns False if the reference does not exist. Child DocumentTemplate rows
    are removed explicitly (also covered by the DB FK ON DELETE CASCADE) so the
    operation is safe regardless of cascade configuration.
    """
    target = await get_reference_document(db, reference_id)
    if target is None:
        return False

    await db.execute(
        delete(DocumentTemplate).where(
            DocumentTemplate.source_doc_id == target.id
        )
    )
    await db.delete(target)
    await db.commit()
    return True
