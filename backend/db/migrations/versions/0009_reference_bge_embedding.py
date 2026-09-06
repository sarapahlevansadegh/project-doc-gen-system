"""add bge_embedding to document_templates for reference<->device matching

Revision ID: 0009_reference_bge_embedding
Revises: 0008_chunk_figure_refs
Create Date: 2026-09-06

Phase 4 prerequisite: reference-document sections (document_templates) are
embedded with MiniLM-L6-v2 (384-dim, `embedding` column) for their own
existing retrieval use case. Device-document chunks (document_chunks) are
embedded with bge-base-en-v1.5 (768-dim). These are two different vector
spaces - cosine similarity between them is meaningless - so a Phase 4 agent
can't directly compare a reference section's embedding to a device chunk's
embedding to find matches.

This adds a second, additional embedding column on document_templates using
bge-base-en-v1.5 (matching document_chunks.embedding's space and dimension),
purely for reference<->device cross-corpus matching. The existing
`embedding` (MiniLM) column and its retrieval path (rag/retriever.py) are
untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0009_reference_bge_embedding"
down_revision: Union[str, None] = "0008_chunk_figure_refs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_templates",
        sa.Column("bge_embedding", Vector(768), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_templates", "bge_embedding")
