"""Generate an SRS draft (JSON) for one device from its typed input files.

From the repo root, with DATABASE_URL set:

    uv run --no-sync python scripts/generate_srs.py \
        --device-id <uuid> \
        --decisions backend/tests/fixtures/vl8_decisions.json \
        --out vl8_srs_draft.json

LLM choice (values come from the shell or from the repo's .env):
  * default: the project's LLMClient (DOCGEN_LLM_PROVIDER, DOCGEN_*_MODEL, keys in .env)
  * IteraCompute: LLM_PROVIDER=iteracompute with ITERACOMPUTE_API_KEY and ITERACOMPUTE_MODEL
    (optional DOCGEN_ITERACOMPUTE_BASE_URL)
  * any other OpenAI-compatible endpoint (most free LLM APIs): set
      DOCGEN_SRS_BASE_URL, DOCGEN_SRS_API_KEY, DOCGEN_SRS_MODEL
    and optionally DOCGEN_SRS_MIN_INTERVAL (seconds between calls) and
    DOCGEN_SRS_TIMEOUT (seconds to wait for one answer, default 180).
Other knobs: DOCGEN_SRS_MAX_TOKENS (output per section), DOCGEN_SRS_MAX_CHARS
(input per section).

Read-only on the database. The device must already have its input files
uploaded with a type (concept, gui_input, ...) and chunked.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

# Make DOCGEN_* values from the repo's .env visible to os.environ (settings.py reads
# .env only for its own fields). Variables already set in the shell are kept.
load_dotenv(BACKEND.parent / ".env", override=False)

import models  # noqa: E402,F401  (registers every mapper)
from core.database import AsyncSessionLocal  # noqa: E402
from services.openai_compatible_llm import (  # noqa: E402
    OpenAICompatibleLLM,
    endpoint_from_env,
)
from services.srs_generator import (  # noqa: E402
    generate_srs_from_chunks,
    load_decisions_file,
    summarize,
)
from services.srs_inputs import load_input_chunks  # noqa: E402


def build_llm():
    try:
        endpoint = endpoint_from_env()
    except ValueError as exc:
        raise SystemExit(str(exc))
    if endpoint is None:
        from agent.llm import LLMClient

        return LLMClient()
    return OpenAICompatibleLLM(
        **endpoint,
        min_interval=float(os.environ.get("DOCGEN_SRS_MIN_INTERVAL", "0")),
        timeout=float(os.environ.get("DOCGEN_SRS_TIMEOUT", "180")),
    )


async def main(device_id: uuid.UUID, decisions_path: Path | None, out: Path,
               include_optional: bool) -> int:
    async with AsyncSessionLocal() as db:
        chunks = await load_input_chunks(db, device_id)
    if not chunks:
        print(f"No typed input chunks for device {device_id}. Check the UUID, the input "
              "types and that chunks were generated.")
        return 1

    by_type: dict[str, int] = {}
    for c in chunks:
        by_type[c.input_type] = by_type.get(c.input_type, 0) + 1
    print("Input chunks by type:", by_type)

    decisions = load_decisions_file(decisions_path) if decisions_path else {}
    llm = build_llm()
    print(f"LLM: {llm.provider} / {llm.model}; decisions: {len(decisions)}")

    drafts = generate_srs_from_chunks(chunks, llm, decisions, include_optional)
    out.write_text(
        json.dumps([d.model_dump(mode="json") for d in drafts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Summary:", json.dumps(summarize(drafts), indent=2))
    print(f"Draft written to {out}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device-id", required=True, type=uuid.UUID)
    parser.add_argument("--decisions", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("srs_draft.json"))
    parser.add_argument("--include-optional", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.device_id, args.decisions, args.out, args.include_optional)))
