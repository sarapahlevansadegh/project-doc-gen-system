"""Add device_documents table for uploaded device files.

Files can be of any type and any size (no restrictions), matching the
same upload experience already used for reference documents.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_device_documents"
down_revision = "0005_cascade_device_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_device_documents_device_id", "device_documents", ["device_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_device_documents_device_id", table_name="device_documents")
    op.drop_table("device_documents")
