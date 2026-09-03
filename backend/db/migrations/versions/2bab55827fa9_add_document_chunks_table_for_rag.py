"""add document_chunks table for RAG

Revision ID: 2bab55827fa9
Revises: 0007_device_document_sections
Create Date: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "2bab55827fa9"
down_revision: Union[str, None] = "0007_device_document_sections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "section_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("device_document_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("device_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_document_chunks_section_id",
        "document_chunks",
        ["section_id"],
    )

def downgrade() -> None:
    op.drop_index("ix_document_chunks_section_id", table_name="document_chunks")
    op.drop_table("document_chunks")