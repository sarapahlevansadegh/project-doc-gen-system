"""Add device_document_id and file hashes to generated_documents (explicit input binding).

Revision ID: 0012_generation_job_device_document
Revises: 0011_ontology_entities
Create Date: 2026-09-19

Generation previously resolved the device's "most recently uploaded"
DeviceDocument implicitly (services/document_generator.py's
generate_document_for_job). This column pins each job to the exact
DeviceDocument it was generated from; the hash columns record the file
content actually read at generation time, so a later re-upload under the
same device_document_id can't silently make an already-completed job's
provenance ambiguous. Nullable at the DB level because it's enforced as
required at the API layer instead (existing rows before this migration
have no value) - see backend/api/routes/documents.py's GenerateRequest.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_generation_job_device_document"
down_revision: Union[str, None] = "0011_ontology_entities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generated_documents",
        sa.Column("device_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "generated_documents_device_document_id_fkey",
        "generated_documents",
        "device_documents",
        ["device_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "generated_documents",
        sa.Column("device_document_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "generated_documents",
        sa.Column("reference_doc_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generated_documents", "reference_doc_hash")
    op.drop_column("generated_documents", "device_document_hash")
    op.drop_constraint(
        "generated_documents_device_document_id_fkey",
        "generated_documents",
        type_="foreignkey",
    )
    op.drop_column("generated_documents", "device_document_id")
