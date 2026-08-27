"""Add device_document_sections table for parsed Device DOCX structure.

Mirrors document_templates (the reference-document section table) but is
keyed off device_documents. Populated right after a Device DOCX upload by
services.device_document_parser (Phase 2.5). No embedding column yet -
turning these rows into searchable RAG chunks is Phase 3.5.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_device_document_sections"
down_revision = "0006_device_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_document_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("device_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_name", sa.String(length=255), nullable=False),
        sa.Column("section_type", sa.String(length=50), nullable=False),
        sa.Column("heading_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_section", sa.String(length=255), nullable=True),
        sa.Column("section_order", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "figure_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_device_document_sections_doc_order",
        "device_document_sections",
        ["document_id", "section_order"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_device_document_sections_doc_order", table_name="device_document_sections"
    )
    op.drop_table("device_document_sections")
