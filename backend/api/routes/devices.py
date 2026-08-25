"""Device management API routes."""
from __future__ import annotations

from api.deps import get_current_active_user, get_db, require_role
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel
from schemas.device import DeviceCreate, DeviceOut, DeviceUpdate
from services import device_document_service, device_service
from sqlalchemy.ext.asyncio import AsyncSession


devices_router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceListResponse(BaseModel):
    items: list[DeviceOut]
    total: int
    skip: int
    limit: int


# ============================================================
# Device CRUD
# ============================================================


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
    return await device_service.list_devices(
        db,
        skip=skip,
        limit=limit,
        search=search,
    )


@devices_router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    device = await device_service.get_device(db, device_id)

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )

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
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )

    device = await device_service.update_device(
        db,
        device,
        payload,
    )

    return device


@devices_router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    device = await device_service.get_device(db, device_id)

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )

    await device_service.delete_device(db, device)


# ============================================================
# Device Documents
# ============================================================


@devices_router.post("/{device_id}/documents")
async def upload_device_document(
    device_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    """
    Upload a DOCX document associated with a device.

    Phase 1:
    - Validate device
    - Validate DOCX file
    - Save file
    - Create DeviceDocument database record

    Document processing / parsing / RAG will be implemented
    in later phases.
    """

    # --------------------------------------------------------
    # Check device
    # --------------------------------------------------------

    device = await device_service.get_device(
        db,
        device_id,
    )

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )

    # --------------------------------------------------------
    # Save document
    # --------------------------------------------------------

    try:
        document = await device_document_service.save_device_document(
            db=db,
            device_id=device.id,
            file=file,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "id": str(document.id),
        "device_id": str(document.device_id),
        "filename": document.filename,
        "file_path": document.file_path,
        "file_type": document.file_type,
        "processing_status": document.processing_status,
        "created_at": document.created_at,
    }