"""Service layer for device document uploads."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from models.device_document import DeviceDocument
from sqlalchemy.ext.asyncio import AsyncSession


ALLOWED_EXTENSIONS = {".docx"}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

UPLOAD_DIR = Path("/app/device_documents")


async def save_device_document(
    db: AsyncSession,
    device_id: uuid.UUID,
    file: UploadFile,
) -> DeviceDocument:

    # Validate extension
    filename = file.filename or ""

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only DOCX files are allowed.")

    # Read file
    content = await file.read()

    # Validate size
    if len(content) > MAX_FILE_SIZE:
        raise ValueError("File size exceeds 10 MB.")

    # Ensure directory exists
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Generate safe filename
    stored_filename = f"{uuid.uuid4()}.docx"

    file_path = UPLOAD_DIR / stored_filename

    # Save file
    file_path.write_bytes(content)

    # Create DB record
    document = DeviceDocument(
        device_id=device_id,
        filename=filename,
        file_path=str(file_path),
        file_type="docx",
        processing_status="uploaded",
    )

    db.add(document)

    await db.commit()
    await db.refresh(document)

    return document