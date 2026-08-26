"""Service layer for uploading files and attaching them to devices.

Mirrors the reference-document upload flow (backend/api/routes/rag.py):
each upload is written to disk under a dedicated storage directory and a
row is created for it. Unlike reference uploads there is no file-type or
file-size restriction here - any file, of any size, can be uploaded.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from models.device import Device
from models.device_document import DeviceDocument
from schemas.device import DeviceCreate
from services import device_service
from sqlalchemy.ext.asyncio import AsyncSession

DEVICE_DOCUMENTS_DIR = Path("device_documents")
DEVICE_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

_CHUNK_SIZE = 1024 * 1024  # 1 MB, streamed to disk so upload size is unbounded


async def _save_upload_to_disk(file: UploadFile, dest: Path) -> int:
    """Stream the upload straight to disk and return the byte count.

    Streaming (instead of reading the whole file into memory first) is what
    lets uploads of any size succeed without hitting memory limits.
    """
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(_CHUNK_SIZE):
            out.write(chunk)
            size += len(chunk)
    return size


async def upload_new_device_document(
    db: AsyncSession,
    file: UploadFile,
) -> Device:
    """Upload a file and create a brand-new device for it.

    This is the "top of page" upload used on the Devices screen, mirroring
    how uploading a reference document creates a new reference row: the
    device name is derived from the uploaded filename, and the resulting
    device (with its document attached) shows up in the device list.
    """
    filename = file.filename or "Untitled"
    device_name = Path(filename).stem or filename

    device = await device_service.create_device(
        db,
        DeviceCreate(name=device_name, specs=[], alarms=[], commands=[]),
    )

    await _attach_document(db, device_id=device.id, file=file, filename=filename)

    return await device_service.get_device(db, str(device.id))


async def _attach_document(
    db: AsyncSession,
    device_id: uuid.UUID,
    file: UploadFile,
    filename: str,
) -> DeviceDocument:
    doc_id = uuid.uuid4()
    dest = DEVICE_DOCUMENTS_DIR / f"{doc_id}_{filename}"

    file_size = await _save_upload_to_disk(file, dest)

    document = DeviceDocument(
        id=doc_id,
        device_id=device_id,
        filename=filename,
        storage_path=str(dest),
        file_size=file_size,
        content_type=file.content_type,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document
