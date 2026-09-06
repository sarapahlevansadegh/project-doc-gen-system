"""Embedding provider for reference-document sections.

Delegates to rag/device_embedding_service.py's bge-base-en-v1.5 singleton
instead of loading a second, separate model. Reference sections
(document_templates) and device-document chunks (document_chunks) are now
embedded with the exact same model, in the same vector space, so they can
be compared directly (see rag/reference_matching.py) - there is no longer
a separate MiniLM-based pipeline to keep apart from this one.
"""
from __future__ import annotations

from rag.device_embedding_service import get_device_embedding_service


def get_embeddings():
    """Kept for backwards-compat call sites; returns the shared bge-base
    embedding service rather than a second, separately-loaded model."""
    return get_device_embedding_service()


async def embed_text(text: str) -> list[float]:
    return get_device_embedding_service().embed_query(text)


async def embed_query(text: str) -> list[float]:
    return get_device_embedding_service().embed_query(text)
