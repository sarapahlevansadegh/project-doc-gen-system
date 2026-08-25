"""add device documents

Revision ID: a12b7a92aea3
Revises: 0005_cascade_device_delete
Create Date: 2026-08-25

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a12b7a92aea3"
down_revision: Union[str, Sequence[str], None] = "0005_cascade_device_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create device_documents table."""

    op.create_table(
        "device_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column(
            "file_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "processing_status",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop device_documents table."""

    op.drop_table("device_documents")