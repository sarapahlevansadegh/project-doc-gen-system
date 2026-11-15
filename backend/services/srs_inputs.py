"""Database access for SRS generation: the input chunks of one device."""
from __future__ import annotations

import uuid

from models.device_document import DeviceDocument, DeviceDocumentSection
from models.document_chunk import DocumentChunk
from services.srs_generator import InputChunk
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def load_input_chunks(db: AsyncSession, device_id: uuid.UUID) -> list[InputChunk]:
    """All chunks of the device's typed input files (files without a type are skipped)."""
    stmt = (
        select(
            DocumentChunk.id,
            DeviceDocument.input_type,
            DeviceDocumentSection.section_name,
            DocumentChunk.chunk_text,
        )
        .join(DeviceDocument, DocumentChunk.device_document_id == DeviceDocument.id)
        .join(DeviceDocumentSection, DocumentChunk.section_id == DeviceDocumentSection.id)
        .where(DeviceDocument.device_id == device_id)
        .where(DeviceDocument.input_type.is_not(None))
        .order_by(DeviceDocument.created_at, DocumentChunk.chunk_index)
    )
    rows = (await db.execute(stmt)).all()
    return [InputChunk(cid, itype, name, text) for cid, itype, name, text in rows]
