"""Optional Vision LLM captioning for FIGURE sections (Phase 3).

Generates a short text caption for an extracted device-document image so
the figure becomes searchable in the RAG embedding space alongside its
surrounding section text. The image itself is never replaced or altered -
the caption is purely supplementary text.

This step is OFF by default (``DOCGEN_ENABLE_FIGURE_CAPTIONING``) because it
costs one LLM call per figure and depends on a third-party vision model.
Deliberately kept separate from ``agent/llm.py``: that abstraction has no
notion of multimodal (image) input, and wiring vision support into every
provider it supports would be significant unrelated churn for a
single-provider (OpenRouter) feature.

Model selection is a comma-separated fallback list rather than one hardcoded
model, because free OpenRouter vision models rotate and rate-limit often.
Known reasoning-heavy models (e.g. GLM-5.3 Flash / "Ox Alpha") are avoided
by default - they have returned empty ``content`` via OpenRouter before
(see agent/llm.py history), which is exactly the failure mode a fail-soft
captioning step must tolerate gracefully rather than crash on.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import os
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

_DEFAULT_VISION_MODELS = "google/gemma-4-31b-it:free,minimax/minimax-m3:free"

_CAPTION_PROMPT = (
    "This image is a figure extracted from a medical device's technical "
    "manual. Describe, in 1-3 concise sentences, what it shows (e.g. a "
    "device diagram, a screen/UI layout, a wiring diagram, a chart) and "
    "any labels or values visible. Do not speculate beyond what is visibly "
    "shown. Respond with the caption text only, no preamble."
)

_MAX_CAPTION_TOKENS = 200


def captioning_enabled() -> bool:
    return os.getenv("DOCGEN_ENABLE_FIGURE_CAPTIONING", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _vision_models() -> list[str]:
    raw = os.getenv("DOCGEN_OPENROUTER_VISION_MODEL", _DEFAULT_VISION_MODELS)
    return [m.strip() for m in raw.split(",") if m.strip()]


def _image_data_url(image_path: str | Path) -> str | None:
    path = Path(image_path)
    if not path.is_file():
        logger.warning("Caption skipped: image file not found at %s", path)
        return None

    mime, _ = mimetypes.guess_type(path.name)
    if mime is None or not mime.startswith("image/"):
        # Docx media files are occasionally saved with non-standard
        # extensions (e.g. a PNG saved as .bin) - default to a safe type
        # rather than refusing to caption an otherwise valid image.
        mime = "image/png"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _call_vision_model(model: str, data_url: str) -> str | None:
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=_MAX_CAPTION_TOKENS,
        temperature=0.2,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _CAPTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        # The empty-content failure mode seen with reasoning-heavy models -
        # treat as a miss so the caller falls through to the next model.
        logger.warning("Vision model '%s' returned empty content", model)
        return None
    return content.strip()


def caption_image(image_path: str | Path) -> str | None:
    """Caption one image, trying each configured model in order.

    Fail-soft by design: any failure (missing file, network error, empty
    response, all models exhausted) returns None rather than raising, so a
    caption problem never blocks the rest of document parsing/embedding.
    Returns None immediately if captioning is disabled or no API key is
    configured.
    """
    if not captioning_enabled():
        return None
    if not settings.openrouter_api_key:
        logger.info("Figure captioning enabled but no OpenRouter API key configured; skipping")
        return None

    data_url = _image_data_url(image_path)
    if data_url is None:
        return None

    for model in _vision_models():
        try:
            caption = _call_vision_model(model, data_url)
        except Exception:
            logger.exception("Vision model '%s' failed captioning %s", model, image_path)
            continue
        if caption:
            return caption

    logger.warning("All configured vision models failed to caption %s", image_path)
    return None
