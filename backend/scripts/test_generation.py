"""Full end-to-end document generation test.

Uses real database, real LLM, real RAG.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

from agent.workflow import generate_document
from core.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    device_id = os.getenv("TEST_DEVICE_ID")
    reference_doc_id = os.getenv("TEST_REFERENCE_DOC_ID")

    if not device_id or not reference_doc_id:
        logger.error("Set TEST_DEVICE_ID and TEST_REFERENCE_DOC_ID env vars")
        return

    logger.info("Starting generation: device=%s reference=%s", device_id, reference_doc_id)

    async with AsyncSessionLocal() as db:
        try:
            result = await generate_document(
                db=db,
                device_id=device_id,
                reference_doc_id=reference_doc_id,
            )
            logger.info("SUCCESS: generated %d sections", len(result["sections"]))
            for name, content in result["sections"].items():
                logger.info("Section: %s (%d chars)", name, len(content))
        except Exception as exc:
            logger.error("FAILED: %s: %s", type(exc).__name__, exc)
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())