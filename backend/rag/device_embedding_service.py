"""
Embedding service for device-document RAG (Phase 3).

Wraps BAAI/bge-base-en-v1.5 via sentence-transformers. Automatically
uses GPU (CUDA) if available, otherwise falls back to CPU.

rag/embeddings.py (the reference-document/template pipeline) now delegates
to this same singleton rather than loading a second model - reference
sections and device chunks are embedded with the same model into the same
vector space on purpose, so a Phase 4 agent can compare them directly (see
rag/reference_bge_embedding.py). There used to be a separate MiniLM-L6-v2
(384-dim) pipeline for reference documents; it was consolidated into this
one (migration 0010_consolidate_reference_embedding) once cross-document
matching required a shared space anyway.
"""
import logging

import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "BAAI/bge-base-en-v1.5"

# bge-base-en-v1.5 requires this instruction prefix on QUERIES only.
# Document/passage text should be embedded with no prefix.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class DeviceEmbeddingService:
    """Loads the device-document embedding model once and reuses it."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(
            "Loading device embedding model '%s' on device '%s'",
            model_name,
            self.device,
        )
        self.model = SentenceTransformer(model_name, device=self.device)
        self.model_name = model_name

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed a batch of device-document chunks (no instruction prefix)."""
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query (with the required instruction prefix)."""
        prefixed = f"{QUERY_INSTRUCTION}{text}"
        embedding = self.model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()


# Module-level singleton so the model is loaded once per process,
# not once per request.
_device_embedding_service: DeviceEmbeddingService | None = None


def get_device_embedding_service() -> DeviceEmbeddingService:
    global _device_embedding_service
    if _device_embedding_service is None:
        _device_embedding_service = DeviceEmbeddingService()
    return _device_embedding_service
