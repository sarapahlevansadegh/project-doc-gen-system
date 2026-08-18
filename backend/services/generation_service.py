"""Generation job service.

Owns the lifecycle of a document-generation job: create, status updates,
progress tracking, and invoking the agent workflow. Stores generated
sections on the job row so results are resumable/inspectable.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from datetime import datetime

from agent.llm import GenerateFn, LLMClient
from agent.workflow import generate_document
from core.database import AsyncSessionLocal
from models.document import GeneratedDocument
from services import docx_builder
from services.device_service import get_device_data
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def create_job(
    db: AsyncSession, device_id: str, reference_doc_id: str
) -> GeneratedDocument:
    max_version = await db.scalar(
        select(func.max(GeneratedDocument.version)).where(
            GeneratedDocument.device_id == uuid.UUID(device_id)
        )
    )
    next_version = (max_version or 0) + 1

    job = GeneratedDocument(
        id=uuid.uuid4(),
        device_id=uuid.UUID(device_id),
        reference_doc_id=uuid.UUID(reference_doc_id),
        status="pending",
        progress_pct=0,
        version=next_version,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: str) -> GeneratedDocument | None:
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        return None
    result = await db.execute(select(GeneratedDocument).where(GeneratedDocument.id == uid))
    return result.scalar_one_or_none()


async def _emit_progress(
    db: AsyncSession, job: GeneratedDocument, event: dict
) -> None:
    job.status = event.get("status", job.status)
    if event.get("section") is not None:
        job.current_section = event["section"]
    if event.get("progress") is not None:
        job.progress_pct = event["progress"]
    await db.commit()


async def run_generation(
    job_id: str,
    generate_fn: GenerateFn | None = None,
    db_factory=AsyncSessionLocal,
    job: GeneratedDocument | None = None,
) -> None:
    """Execute the workflow for a job in a dedicated background session.

    The caller must NOT pass a request-scoped session: this coroutine opens
    its own session via ``db_factory`` (defaulting to ``AsyncSessionLocal``)
    so it can outlive the HTTP request that scheduled it. The job row is
    reloaded by id inside that session; an in-memory ``job`` may be supplied
    for tests instead of reloading from the database.
    """
    try:
        logger.info("run_generation started: job_id=%s", job_id)
        llm = LLMClient(generate_fn=generate_fn)
        logger.info("LLMClient initialized: provider=%s model=%s", llm.provider, llm.model)

        if job is not None:
            async with db_factory() as db:
                job.status = "processing"
                await db.commit()
                logger.info("Job status set to processing (in-memory job)")
                await _run_workflow(db, job, llm)
            logger.info("run_generation completed (in-memory job)")
            return

        async with db_factory() as db:
            logger.info("Database session opened")
            result = await db.execute(
                select(GeneratedDocument).where(GeneratedDocument.id == uuid.UUID(job_id))
            )
            job = result.scalar_one_or_none()
            if job is None:
                logger.warning("Job not found: job_id=%s", job_id)
                return
            logger.info("Job loaded: job_id=%s device_id=%s reference_doc_id=%s", job.id, job.device_id, job.reference_doc_id)
            job.status = "processing"
            await db.commit()
            logger.info("Job status set to processing")
            await _run_workflow(db, job, llm)
        logger.info("run_generation completed: job_id=%s", job_id)
    except Exception:
        logger.error("run_generation failed: job_id=%s", job_id)
        traceback.print_exc()
        raise


async def _run_workflow(
    db: AsyncSession, job: GeneratedDocument, llm: LLMClient
) -> None:
    """Run the agent workflow for ``job`` and persist progress/result."""
    async def progress_callback(event: dict) -> None:
        await _emit_progress(db, job, event)

    try:
        result = await generate_document(
            db=db,
            device_id=str(job.device_id),
            reference_doc_id=str(job.reference_doc_id),
            llm_client=llm,
            progress_callback=progress_callback,
        )
        job.result_sections = result["sections"]
        logger.info("Document generation completed: sections=%s", len(job.result_sections))

        logger.info("Loading device data for DOCX build")
        device_data = await get_device_data(db, str(job.device_id))
        output_data = {"device_data": device_data, "sections": job.result_sections}

        logger.info("Building DOCX document")
        job.file_path = await asyncio.to_thread(docx_builder.build_document, output_data)
        logger.info("DOCX built: file_path=%s", job.file_path)

        logger.info("Saving output")
        job.status = "completed"
        job.progress_pct = 100
        job.current_section = None
        job.completed_at = datetime.utcnow()
        await db.commit()
        logger.info("Job completed successfully: job_id=%s", job.id)
    except Exception as exc:
        logger.error("_run_workflow failed: job_id=%s error=%s", job.id, exc)
        traceback.print_exc()
        job.status = "failed"
        job.error_message = str(exc)
        await db.commit()
        raise
