"""consolidate document_templates to a single bge-base-en-v1.5 embedding

Revision ID: 0010_consolidate_reference_embedding
Revises: 0009_reference_bge_embedding
Create Date: 2026-09-06

Decision: rather than maintaining two embedding columns on
document_templates (MiniLM `embedding` for its own retrieval, bge-base
`bge_embedding` for cross-corpus matching against device_document chunks
- added in 0009), drop the MiniLM pipeline entirely and embed reference
sections with bge-base-en-v1.5 directly in `embedding`. This is also what
settings.embed_model/EMBED_MODEL already default to in docker-compose.yml
(BAAI/bge-base-en-v1.5) - the old `embedding vector(384)` column was
already out of sync with the model actually configured to run.

Existing embedding values are dropped, not migrated - a MiniLM vector
can't be reinterpreted as a bge-base vector (different model, different
space). Any existing reference documents need their sections re-embedded
after this migration (re-upload, or a future re-embed script/endpoint).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0010_consolidate_reference_embedding"
down_revision: Union[str, None] = "0009_reference_bge_embedding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("document_templates", "bge_embedding")
    op.drop_column("document_templates", "embedding")
    op.add_column(
        "document_templates",
        sa.Column("embedding", Vector(768), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_templates", "embedding")
    op.add_column(
        "document_templates",
        sa.Column("embedding", Vector(384), nullable=True),
    )
    op.add_column(
        "document_templates",
        sa.Column("bge_embedding", Vector(768), nullable=True),
    )
