"""Add version column to generated_documents.

Revision ID: 0003_document_version
Depends on: 0002_generation_job
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_document_version"
down_revision = "0002_generation_job"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_documents",
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("generated_documents", "version")
