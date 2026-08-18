"""Agent workflow: device -> reference sections -> RAG context -> LLM -> result.

Sections are discovered dynamically from the reference document (no hardcoded
section names). Progress is reported through an optional async callback.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Callable

from models.template import DocumentTemplate
from rag.retriever import retrieve_similar_sections
from services.device_service import get_device_data
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.llm import LLMClient
from agent.prompts import build_section_prompt

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[dict], None]

DEFAULT_RETRIEVE_K = 3


async def discover_reference_sections(
    db: AsyncSession, reference_doc_id: str
) -> list[DocumentTemplate]:
    """Load reference sections in document order (dynamic discovery)."""
    result = await db.execute(
        select(DocumentTemplate)
        .where(DocumentTemplate.source_doc_id == reference_doc_id)
        .order_by(DocumentTemplate.section_order)
    )
    return list(result.scalars().all())


async def generate_document(
    db: AsyncSession,
    device_id: str,
    reference_doc_id: str,
    llm_client: LLMClient | None = None,
    progress_callback: ProgressCallback | None = None,
    retrieve_k: int = DEFAULT_RETRIEVE_K,
) -> dict:
    """Run the full generation workflow and return {device_data, sections}."""
    try:
        logger.info("generate_document started: device_id=%s reference_doc_id=%s", device_id, reference_doc_id)
        llm = llm_client or LLMClient()
        logger.info("LLM provider=%s model=%s", llm.provider, llm.model)

        logger.info("Loading device data: device_id=%s", device_id)
        device_data = await get_device_data(db, device_id)
        logger.info("Device loaded: name=%s", device_data.get("name"))
        if progress_callback:
            await progress_callback(
                {"status": "processing", "section": None, "progress": 0,
                 "message": f"Loaded device {device_data['name']}"}
            )

        logger.info("Discovering reference sections: reference_doc_id=%s", reference_doc_id)
        ref_sections = await discover_reference_sections(db, reference_doc_id)
        if not ref_sections:
            raise ValueError(f"No reference sections found for {reference_doc_id}")
        logger.info("Reference sections discovered: count=%s", len(ref_sections))

        generated = {}
        total = len(ref_sections)

        for index, ref in enumerate(ref_sections):
            section_name = ref.section_name
            logger.info("Processing section %s/%s: %s", index + 1, total, section_name)

            logger.info("Retrieving similar sections for: %s", section_name)
            similar = await retrieve_similar_sections(
                db,
                query=f"{section_name} {device_data['name']}",
                k=retrieve_k,
                reference_doc_id=reference_doc_id,
            )
            logger.info("Retrieved %s similar sections", len(similar))

            prompt = build_section_prompt(
                section_name=section_name,
                reference_content=ref.content,
                device_data=device_data,
                similar_context=similar,
            )

            if progress_callback:
                await progress_callback(
                    {"status": "processing", "section": section_name, "progress": 0,
                     "message": f"Generating section: {section_name}"}
                )

            logger.info(
                "LLM prompt built: prompt_len=%d prompt_preview=%r ref_content_len=%d similar_context_len=%d max_tokens=%d temperature=%.2f",
                len(prompt),
                prompt[:300],
                len(ref.content),
                sum(len(s) for s in similar),
                2000,
                0.3,
            )
            logger.info("Calling LLM for section: %s", section_name)
            content = await asyncio.to_thread(
                llm.generate, prompt, 2000, 0.3
            )
            logger.info("LLM response received for section: %s (length=%s)", section_name, len(content))
            generated[section_name] = content.strip()

            if progress_callback:
                pct = int((index + 1) / total * 100)
                await progress_callback(
                    {"status": "processing", "section": section_name,
                     "progress": pct,
                     "message": f"Completed section: {section_name}"}
                )

        logger.info("generate_document completed successfully")
        return {"device_data": device_data, "sections": generated}
    except Exception:
        logger.error("generate_document failed")
        traceback.print_exc()
        raise
