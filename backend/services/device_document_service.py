"""Service layer for uploading files and attaching them to devices.

Mirrors the reference-document upload flow (backend/api/routes/rag.py):
each upload is written to disk under a dedicated storage directory and a
row is created for it. Uploads are restricted to a whitelist of document
extensions, capped at ``settings.max_device_document_upload_bytes``, and
the on-disk filename is sanitized so a crafted ``filename`` cannot escape
``DEVICE_DOCUMENTS_DIR`` (path traversal).
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from config import settings
from fastapi import HTTPException, UploadFile
from models.device import Device
from models.device_document import DeviceDocument
from schemas.device import DeviceCreate
from services import device_document_parser, device_service
from sqlalchemy.ext.asyncio import AsyncSession

DEVICE_DOCUMENTS_DIR = Path("device_documents")
DEVICE_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

_CHUNK_SIZE = 1024 * 1024  # 1 MB, streamed to disk in bounded increments

ALLOWED_EXTENSIONS = {".docx", ".doc", ".pdf"}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(filename: str) -> str:
    """Reduce a user-supplied filename to a safe basename.

    Strips any directory components (defeats ``../`` path traversal) and
    replaces characters outside a conservative whitelist, so the value is
    safe to use verbatim in an on-disk path.
    """
    name = Path(filename).name  # drop any directory components
    name = _UNSAFE_CHARS.sub("_", name).strip("._") or "file"
    return name


def _validate_extension(filename: str) -> None:
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed extensions: {allowed}",
        )


async def _save_upload_to_disk(file: UploadFile, dest: Path) -> int:
    """Stream the upload to disk, enforcing the configured size cap.

    Streaming (instead of reading the whole file into memory first) keeps
    memory use bounded; checking the running total against the cap on each
    chunk stops oversized uploads early instead of filling the disk.
    """
    limit = settings.max_device_document_upload_bytes
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {limit // (1024 * 1024)} MB upload limit",
                    )
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
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
    _validate_extension(filename)
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
    safe_filename = _sanitize_filename(filename)
    dest = DEVICE_DOCUMENTS_DIR / f"{doc_id}_{safe_filename}"

    file_size = await _save_upload_to_disk(file, dest)

    document = DeviceDocument(
        id=doc_id,
        device_id=device_id,
        filename=safe_filename,
        storage_path=str(dest),
        file_size=file_size,
        content_type=file.content_type,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Best-effort structural parse (Phase 2.5): failures here must not roll
    # back or fail the upload itself, since the file is already saved and
    # attached - parse_and_store_sections already swallows its own errors.
    await device_document_parser.parse_and_store_sections(
        db, document_id=document.id, storage_path=document.storage_path
    )

    return document
