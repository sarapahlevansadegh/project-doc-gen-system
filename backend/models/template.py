import uuid
from datetime import datetime
from enum import Enum

from core.database import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class SectionType(str, Enum):
    TEXT = "TEXT"
    TABLE = "TABLE"
    FIGURE = "FIGURE"
    REQUIREMENT = "REQUIREMENT"
    INTERFACE = "INTERFACE"
    ALARM = "ALARM"


class ReferenceDocument(Base):
    __tablename__ = "reference_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=True)
    section_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentTemplate(Base):
    """Stored document section (RAG chunk).

    Conceptually this table holds *sections* of a reference document.
    `DocumentSection` is provided as the preferred alias.
    """

    __tablename__ = "document_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reference_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_name: Mapped[str] = mapped_column(String(255), nullable=False)
    section_type: Mapped[str] = mapped_column(String(50), default=SectionType.TEXT.value)
    heading_level: Mapped[int] = mapped_column(Integer, default=1)
    parent_section: Mapped[str] = mapped_column(String(255), nullable=True)
    section_order: Mapped[int] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    figure_refs: Mapped[list] = mapped_column(JSONB, default=list)
    embedding: Mapped[list] = mapped_column(Vector(384), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=True)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=True)
    meta_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_document_templates_source_order", "source_doc_id", "section_order"),
    )


# Preferred conceptual name for a stored document section.
DocumentSection = DocumentTemplate

