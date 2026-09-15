"""Generation job service.

Owns the lifecycle of a document-generation job: create, status updates,
progress tracking, and invoking the document generator. Stores generated
sections on the job row so results are resumable/inspectable.

_run_workflow() calls services/document_generator.py (Phase 5's edit-the-
actual-reference-.docx approach, built on top of
services/document_diff_planner.py's tested matching/prompt/guardrail
logic), not the older agent/workflow.py + services/docx_builder.py path.
That older path rebuilds a document from scratch via free-form LLM
generation per section (no rule against changing the reference's wording,
and no preservation of the original file's real Word formatting/tables/
images) - it's being kept in the codebase in case it's ever useful for a
different purpose, but this job pipeline no longer calls it.
"""
from __future__ import annotations

import logging
import traceback
import uuid
from datetime import datetime

from agent.llm import GenerateFn, LLMClient
from core.database import AsyncSessionLocal
from models.document import GeneratedDocument
from services import document_generator
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
    """Run document_generator's Phase 5 pipeline for ``job`` and persist
    progress/result."""
    async def progress_callback(event: dict) -> None:
        await _emit_progress(db, job, event)

    try:
        result = await document_generator.generate_document_for_job(
            db,
            device_id=job.device_id,
            reference_doc_id=job.reference_doc_id,
            llm=llm,
            progress_callback=progress_callback,
        )
        job.result_sections = result["sections"]
        job.file_path = str(result["output_path"])
        logger.info(
            "Document generation completed: sections=%s file_path=%s",
            len(job.result_sections), job.file_path,
        )

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
