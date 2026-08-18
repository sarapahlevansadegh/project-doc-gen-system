"""Document generation API routes."""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from api.deps import get_current_active_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from models.device import Device
from models.document import GeneratedDocument
from models.template import ReferenceDocument
from pydantic import BaseModel
from rag.retriever import get_active_reference
from services import generation_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

documents_router = APIRouter(prefix="/documents", tags=["documents"])


class GenerateRequest(BaseModel):
    device_id: uuid.UUID
    reference_document_id: uuid.UUID | None = None


class GenerateResponse(BaseModel):
    job_id: str
    status: str


class SectionOut(BaseModel):
    name: str
    content: str


class DocumentStatusOut(BaseModel):
    job_id: str
    status: str
    progress: int
    current_section: str | None
    result: list[SectionOut] | None
    error_message: str | None


class DocumentHistoryOut(BaseModel):
    job_id: str
    version: int
    status: str
    created_at: str | None
    completed_at: str | None


@documents_router.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate_document(
    payload: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "engineer")),
):
    device_exists = await db.scalar(
        select(Device.id).where(Device.id == payload.device_id)
    )
    if device_exists is None:
        raise HTTPException(status_code=404, detail="Device not found")

    ref_id = payload.reference_document_id
    if ref_id is None:
        active = await get_active_reference(db)
        if active is None:
            raise HTTPException(
                status_code=404, detail="No active reference document found"
            )
        ref_id = active.id
    else:
        ref_exists = await db.scalar(
            select(ReferenceDocument.id).where(
                ReferenceDocument.id == ref_id
            )
        )
        if ref_exists is None:
            raise HTTPException(status_code=404, detail="Reference document not found")

    job = await generation_service.create_job(
        db, str(payload.device_id), str(ref_id)
    )
    # run generation in the background using its OWN session (never the
    # request-scoped session, which is closed after we return 202)
    logger.info("Scheduling generation task for job_id=%s", job.id)
    task = asyncio.create_task(
        generation_service.run_generation(str(job.id))
    )
    task.add_done_callback(_log_generation_task_result)
    logger.info("Task scheduled: job_id=%s", job.id)
    return GenerateResponse(job_id=str(job.id), status=job.status)


def _log_generation_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Background document generation task failed")


@documents_router.get("/{job_id}", response_model=DocumentStatusOut)
async def get_document_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    job = await generation_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    result = None
    if job.result_sections:
        result = [
            SectionOut(name=name, content=content)
            for name, content in job.result_sections.items()
        ]

    return DocumentStatusOut(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress_pct,
        current_section=job.current_section,
        result=result,
        error_message=job.error_message,
    )


@documents_router.get("/{job_id}/download")
async def download_document(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    job = await generation_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not ready for download (status: {job.status})",
        )

    if not job.file_path:
        raise HTTPException(status_code=404, detail="Document file not found")

    file_path = Path(job.file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found")

    return FileResponse(
        str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@documents_router.get("/history/{device_id}", response_model=list[DocumentHistoryOut])
async def get_document_history(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid device ID")

    device_exists = await db.scalar(select(Device.id).where(Device.id == device_uuid))
    if device_exists is None:
        raise HTTPException(status_code=404, detail="Device not found")

    result = await db.execute(
        select(GeneratedDocument)
        .where(GeneratedDocument.device_id == device_uuid)
        .order_by(GeneratedDocument.version.desc())
    )
    jobs = result.scalars().all()

    return [
        DocumentHistoryOut(
            job_id=str(job.id),
            version=job.version,
            status=job.status,
            created_at=job.created_at.isoformat() if job.created_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
        )
        for job in jobs
    ]
