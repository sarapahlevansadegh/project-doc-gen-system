"""RAG reference-document ingestion API."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from api.deps import get_current_active_user, get_db, require_role
from config import settings
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from models.template import DocumentTemplate, ReferenceDocument
from pydantic import BaseModel
from rag.extractor import extract_docx
from rag.reference_bge_embedding import find_matching_device_chunks, generate_bge_embeddings
from rag.retriever import (
    delete_reference,
    get_active_reference,
    set_active_reference,
    store_sections,
)
from rag.splitter import split_sections
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

rag_router = APIRouter(prefix="/rag", tags=["rag"])

REFERENCE_DIR = Path("reference_templates")
REFERENCE_DIR.mkdir(parents=True, exist_ok=True)


class ReferenceOut(BaseModel):
    id: uuid.UUID
    filename: str
    template_name: str
    section_count: int
    version: int
    is_active: bool
    created_at: datetime | None

    model_config = {"from_attributes": True}


class SectionOut(BaseModel):
    section_name: str
    section_type: str
    heading_level: int
    parent_section: str | None
    section_order: int
    content_preview: str

    @classmethod
    def from_row(cls, row: DocumentTemplate) -> SectionOut:
        return cls(
            section_name=row.section_name,
            section_type=row.section_type,
            heading_level=row.heading_level,
            parent_section=row.parent_section,
            section_order=row.section_order,
            content_preview=row.content[:200],
        )


@rag_router.post("/reference", response_model=ReferenceOut)
async def upload_reference(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    ref_id = uuid.uuid4()
    dest = REFERENCE_DIR / f"{ref_id}_{file.filename}"
    content = await file.read()
    dest.write_bytes(content)

    sections = extract_docx(str(dest))
    rag_sections = split_sections(sections)

    ref = ReferenceDocument(
        id=ref_id,
        filename=file.filename,
        template_name=Path(file.filename).stem,
        storage_path=str(dest),
        version=1,
        is_active=True,
        embedding_model=settings.embed_model,
        embedding_dimension=settings.embed_dimension,
    )
    db.add(ref)
    await db.flush()

    await store_sections(
        db=db,
        reference_doc_id=ref.id,
        template_name=ref.template_name,
        sections=rag_sections,
    )
    await db.refresh(ref)
    return ref


@rag_router.get("/reference", response_model=list[ReferenceOut])
async def list_references(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    result = await db.execute(select(ReferenceDocument).order_by(ReferenceDocument.created_at.desc()))
    return result.scalars().all()


@rag_router.get("/reference/{reference_id}/sections", response_model=list[SectionOut])
async def list_sections(
    reference_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    result = await db.execute(
        select(DocumentTemplate)
        .where(DocumentTemplate.source_doc_id == reference_id)
        .order_by(DocumentTemplate.section_order)
    )
    return [SectionOut.from_row(r) for r in result.scalars().all()]


class GenerateBgeEmbeddingsResponse(BaseModel):
    reference_id: uuid.UUID
    section_count: int


@rag_router.post(
    "/reference/{reference_id}/bge-embeddings",
    response_model=GenerateBgeEmbeddingsResponse,
)
async def generate_reference_bge_embeddings(
    reference_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    """Phase 4 prerequisite: (re)compute bge-base-en-v1.5 embeddings for this
    reference document's sections, so they're in the same vector space as
    device_document chunks and can be matched against them. Does not affect
    the existing MiniLM-based `embedding` column or its retrieval path.
    """
    count = await generate_bge_embeddings(db, reference_id)
    if count == 0:
        raise HTTPException(
            status_code=404, detail="Reference document has no sections to embed"
        )
    return GenerateBgeEmbeddingsResponse(reference_id=reference_id, section_count=count)


class MatchingChunkOut(BaseModel):
    chunk_id: int
    chunk_index: int
    content_preview: str
    similarity: float
    figures: list[dict]

    @classmethod
    def from_dict(cls, d: dict) -> "MatchingChunkOut":
        return cls(
            chunk_id=d["chunk_id"],
            chunk_index=d["chunk_index"],
            content_preview=d["chunk_text"][:200],
            similarity=d["similarity"],
            figures=d["figure_refs"] or [],
        )


@rag_router.get(
    "/reference/sections/{section_id}/matches",
    response_model=list[MatchingChunkOut],
)
async def get_matching_device_chunks(
    section_id: uuid.UUID,
    device_document_id: uuid.UUID = Query(...),
    k: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Phase 4: the k device-document chunks most semantically similar to
    one reference section, within a specific device document. Returns []
    if the reference section has no bge_embedding yet - call
    POST /rag/reference/{reference_id}/bge-embeddings first.
    """
    matches = await find_matching_device_chunks(db, section_id, device_document_id, k=k)
    return [MatchingChunkOut.from_dict(m) for m in matches]


@rag_router.get("/reference/active", response_model=ReferenceOut | None)
async def get_active_reference_endpoint(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Return the currently active reference document (or null if none)."""

    return await get_active_reference(db)


@rag_router.post("/reference/{reference_id}/activate", response_model=ReferenceOut)
async def activate_reference(
    reference_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    """Mark one reference active; deactivate all others (only one active)."""

    ref = await set_active_reference(db, reference_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Reference document not found")
    return ref


@rag_router.delete("/reference/{reference_id}", status_code=204)
async def delete_reference_endpoint(
    reference_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    """Delete a reference and its stored sections/embeddings."""

    deleted = await delete_reference(db, reference_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reference document not found")
