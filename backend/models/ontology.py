"""SQLAlchemy models for the Phase 3.5 ontology / knowledge-graph layer.

Persists the output of ontology/extractor.py's extract_entities() /
extract_relationships() (see that module's docstring - those are pure
functions with no storage of their own). Scoped by device_id, not
device_document_id, so a fact extracted from one document is comparable
against a fact extracted from another document for the same device - see
db/migrations/versions/0011_ontology_entities.py for the schema this
mirrors and the reasoning behind that choice.

NOTE: this file was missing from git (backend/.gitignore has a broad
`models/` rule - see project memory). models/__init__.py, the ontology
extraction service, and its tests all already import from here, so
without this file the app fails to import at all. Use `git add -f` when
committing this file.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from core.database import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class OntologyEntity(Base):
    __tablename__ = "ontology_entities"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "entity_type", "value",
            name="uq_ontology_entity_device_type_value",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    source_chunk_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class OntologyRelationship(Base):
    __tablename__ = "ontology_relationships"
    __table_args__ = (
        UniqueConstraint(
            "subject_id", "relation", "object_id",
            name="uq_ontology_relationship_triple",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(String(100), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_chunk_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
