"""Add input_type and processing status to device_documents (multi-file device inputs).

Revision ID: 0013_device_document_input_type
Revises: 0012_generation_job_device_document
Create Date: 2026-10-17

A device can now carry several input files (concept, GUI input, driver
input, hardware design, other), each tagged with a type chosen by the
engineer. ``processing_status`` records what happened to the structural
parse of each file (parsed / skipped / failed) so the UI can show it.
All columns are nullable: rows uploaded before this migration have no type
or status.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_device_document_input_type"
down_revision: Union[str, None] = "0012_generation_job_device_document"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "device_documents",
        sa.Column("input_type", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "device_documents",
        sa.Column("processing_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "device_documents",
        sa.Column("processing_note", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("device_documents", "processing_note")
    op.drop_column("device_documents", "processing_status")
    op.drop_column("device_documents", "input_type")
