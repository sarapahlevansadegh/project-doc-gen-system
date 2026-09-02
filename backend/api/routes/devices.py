"""Device management API routes."""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from api.deps import get_current_active_user, get_db, require_role
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from models.device_document import DeviceDocumentSection
from pydantic import BaseModel
from schemas.device import DeviceCreate, DeviceOut, DeviceUpdate
from services import device_document_service, device_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

devices_router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceListResponse(BaseModel):
    items: list[DeviceOut]
    total: int
    skip: int
    limit: int


class DeviceDocumentFigureOut(BaseModel):
    rel_id: str
    alt_text: str | None = None
    image_url: str | None = None


class DeviceDocumentSectionOut(BaseModel):
    section_name: str
    section_type: str
    heading_level: int
    parent_section: str | None
    section_order: int | None
    content_preview: str
    figures: list[DeviceDocumentFigureOut]

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: DeviceDocumentSection) -> "DeviceDocumentSectionOut":
        # Only expose a figure once its bytes were actually extracted
        # (image_path present) - a figure_refs entry without one means
        # extraction failed or skipped it, and there's nothing to link to.
        figures = [
            DeviceDocumentFigureOut(
                rel_id=fig["rel_id"],
                alt_text=fig.get("alt_text"),
                image_url=f"/devices/documents/{row.document_id}/images/{fig['rel_id']}",
            )
            for fig in (row.figure_refs or [])
            if fig.get("rel_id") and fig.get("image_path")
        ]
        return cls(
            section_name=row.section_name,
            section_type=row.section_type,
            heading_level=row.heading_level,
            parent_section=row.parent_section,
            section_order=row.section_order,
            content_preview=row.content[:200],
            figures=figures,
        )


@devices_router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
    payload: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    device = await device_service.create_device(db, payload)
    return device


@devices_router.get("", response_model=DeviceListResponse)
async def list_devices(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=100),
):
    return await device_service.list_devices(db, skip=skip, limit=limit, search=search)


@devices_router.post("/documents", response_model=DeviceOut, status_code=201)
async def upload_device_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    """Upload a file and create a new device for it (any file, any size).

    Mirrors the "Upload Reference" flow: the uploaded file becomes a new
    entry in the device list, named after the file.
    """
    return await device_document_service.upload_new_device_document(db, file)


@devices_router.get(
    "/documents/{document_id}/sections", response_model=list[DeviceDocumentSectionOut]
)
async def list_device_document_sections(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Structural sections extracted from an uploaded Device DOCX (Phase 2.5).

    Empty for non-.docx uploads (.doc/.pdf) or if extraction failed - see
    services.device_document_parser.
    """
    result = await db.execute(
        select(DeviceDocumentSection)
        .where(DeviceDocumentSection.document_id == document_id)
        .order_by(DeviceDocumentSection.section_order)
    )
    rows = result.scalars().all()
    return [DeviceDocumentSectionOut.from_row(row) for row in rows]


@devices_router.get(
    "/documents/{document_id}/images/{rel_id}",
)
async def get_device_document_image(
    document_id: uuid.UUID,
    rel_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Serve one extracted image from a Device DOCX (Phase 2.5, Part B).

    The on-disk path is never taken from the request - ``rel_id`` is only
    resolved against this specific document's own ``figure_refs`` rows, so
    a client can only ever reach an image this document actually extracted,
    not an arbitrary path on the server.
    """
    result = await db.execute(
        select(DeviceDocumentSection.figure_refs).where(
            DeviceDocumentSection.document_id == document_id
        )
    )
    image_path: str | None = None
    for (figure_refs,) in result.all():
        for fig in figure_refs or []:
            if fig.get("rel_id") == rel_id and fig.get("image_path"):
                image_path = fig["image_path"]
                break
        if image_path:
            break

    if image_path is None:
        raise HTTPException(status_code=404, detail="Image not found")

    path = Path(image_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing on disk")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Response(content=path.read_bytes(), media_type=media_type)


@devices_router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    device = await device_service.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@devices_router.patch("/{device_id}", response_model=DeviceOut)
async def patch_device(
    device_id: str,
    payload: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    device = await device_service.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device = await device_service.update_device(db, device, payload)
    return device


@devices_router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    device = await device_service.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    await device_service.delete_device(db, device)
