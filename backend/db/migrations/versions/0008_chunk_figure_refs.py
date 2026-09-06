"""add figure_refs to document_chunks

Revision ID: 0008_chunk_figure_refs
Revises: b1e9a7bf3114
Create Date: 2026-09-06

Direct chunk <-> image linkage (Phase 4 prerequisite): every chunk
generated from a section now carries that section's figure_refs (rel_id,
alt_text, image_path, caption), so an agent working from a chunk doesn't
need an extra hop through device_document_sections to find its images.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0008_chunk_figure_refs"
down_revision: Union[str, None] = "b1e9a7bf3114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("figure_refs", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "figure_refs")
