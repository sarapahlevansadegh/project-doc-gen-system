"""Add generation job fields to generated_documents.

Revision ID: 0002_generation_job
Depends on: 0001_initial
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_generation_job"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_documents",
        sa.Column(
            "reference_doc_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reference_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "generated_documents", sa.Column("progress_pct", sa.Integer, server_default="0")
    )
    op.add_column(
        "generated_documents", sa.Column("current_section", sa.String(255), nullable=True)
    )
    op.add_column(
        "generated_documents", sa.Column("result_sections", postgresql.JSONB, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("generated_documents", "result_sections")
    op.drop_column("generated_documents", "current_section")
    op.drop_column("generated_documents", "progress_pct")
    op.drop_column("generated_documents", "reference_doc_id")
