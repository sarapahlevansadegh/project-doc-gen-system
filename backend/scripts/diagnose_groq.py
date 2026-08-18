"""Isolated diagnostic: test minimal prompts to isolate Groq 403 trigger.

This script does NOT modify any production code.
Uses the same GROQ_API_KEY and model: llama-3.3-70b-versatile.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from agent.llm import LLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run_test(name: str, prompt: str) -> None:
    provider = "groq"
    model = "llama-3.3-70b-versatile"
    logger.info("=== TEST: %s ===", name)
    logger.info("prompt_len=%d", len(prompt))
    logger.info("prompt=%r", prompt[:200])
    llm = LLMClient(provider=provider, model=model)
    try:
        content = llm.generate(prompt, max_tokens=2000, temperature=0.3)
        logger.info("SUCCESS: response_len=%d", len(content))
        print(f"=== {name} SUCCESS ===")
        print(content[:300])
    except Exception as exc:
        logger.error("FAILED: %s: %s", type(exc).__name__, exc)
        if hasattr(exc, "response") and exc.response is not None:
            logger.error("Response status: %s", exc.response.status_code)
            logger.error("Response body: %s", exc.response.text)
        print(f"=== {name} FAILED: 403 ===")


async def main() -> None:
    tests = [
        (
            "test1_minimal",
            "Reply only TEST_OK",
        ),
        (
            "test2_medical_role",
            "You are a medical device software documentation engineer. Reply only TEST_OK.",
        ),
        (
            "test3_generic_sad",
            "Generate a Software Architectural Design section for a medical device. Reply only TEST_OK.",
        ),
        (
            "test4_iec_term",
            "IEC 62304 medical device software documentation. Reply only TEST_OK.",
        ),
        (
            "test5_full_1479",
            """You are an expert medical device software documentation engineer.

Generate the '1.1 LCD Module' section for a Software Architectural Design document.

# NEW DEVICE INFORMATION
Name: VL8
Model: VL8
Document Code: 15799
Safety Class: B
Driver Version: 01
GUI Version: 7.0.0.7650

Specifications:
  - wavelength_a: 808 nm
  - wavelength_b: 1064 nm
  - max_power: 8 W
  - switch_type: Handswitch

Alarms:
  - [High] Laser temperature > 45°C

Serial Commands:
  - START

# REFERENCE SECTION (preserve its structure, headings and professional tone)
The device runs a layered software architecture. The LCD module renders status and warnings. Serial link uses RS-232 at 115200 baud. Driver and Qt specifications table.

# SIMILAR REFERENCE SECTIONS (additional context)
Reference LCD content about touch display.
Reference RS-232 details.

# INSTRUCTIONS
- Follow the exact structure, numbering, and professional engineering tone of the reference section.
- Replace all device-specific details (wavelengths, power, switch type, modules, commands) with the NEW device's values above.
- Keep all IEC 62304 / regulatory compliance language intact.
- Be technically accurate and internally consistent with the device information.
- Use formal English throughout.
- Only use specifications provided in the device information; do not invent technical specs.
- Do not include phrases such as "Here is the generated section".
- Generate only the final content of the '1.1 LCD Module' section.
""",
        ),
    ]

    for name, prompt in tests:
        await run_test(name, prompt)
        print()


if __name__ == "__main__":
    asyncio.run(main())