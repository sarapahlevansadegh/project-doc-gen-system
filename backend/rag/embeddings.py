"""Embedding provider wrapper (configurable, singleton)."""
from __future__ import annotations

from functools import lru_cache

from config import settings
from langchain_huggingface import HuggingFaceEmbeddings


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.embed_model)


async def embed_text(text: str) -> list[float]:
    return get_embeddings().embed_query(text)


async def embed_query(text: str) -> list[float]:
    return get_embeddings().embed_query(text)
