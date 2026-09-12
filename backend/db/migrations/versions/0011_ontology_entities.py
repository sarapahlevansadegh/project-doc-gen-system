"""add ontology_entities and ontology_relationships tables (Phase 3.5.9)

Revision ID: 0011_ontology_entities
Revises: 0010_consolidate_reference_embedding
Create Date: 2026-09-12

Persists the output of ontology/extractor.py's extract_entities() /
extract_relationships() (previously pure functions with no storage - see
ontology/schema.py's docstring). Scoped by device_id rather than
device_document_id so a fact extracted from one document is comparable
against a fact extracted from another document for the same device -
this is what makes a cross-document consistency check (e.g. a GUI-version
value stated differently in two documents for the same device) possible
at all. source_chunk_id is kept for provenance and to still allow
scoping down to a single document's chunks when needed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_ontology_entities"
down_revision: Union[str, None] = "0010_consolidate_reference_embedding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ontology_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column(
            "source_chunk_id",
            sa.Integer(),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "device_id", "entity_type", "value", name="uq_ontology_entity_device_type_value"
        ),
    )
    op.create_index(
        "ix_ontology_entities_device_id", "ontology_entities", ["device_id"]
    )

    op.create_table(
        "ontology_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(length=100), nullable=False),
        sa.Column(
            "object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_chunk_id",
            sa.Integer(),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "subject_id", "relation", "object_id", name="uq_ontology_relationship_triple"
        ),
    )
    op.create_index(
        "ix_ontology_relationships_device_id", "ontology_relationships", ["device_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ontology_relationships_device_id", table_name="ontology_relationships")
    op.drop_table("ontology_relationships")
    op.drop_index("ix_ontology_entities_device_id", table_name="ontology_entities")
    op.drop_table("ontology_entities")
