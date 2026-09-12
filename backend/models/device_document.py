import uuid
from datetime import datetime

from core.database import Base
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# s
class DeviceDocument(Base):
    """A file uploaded and attached to a device (any file type, any size)."""

    __tablename__ = "device_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device: Mapped["Device"] = relationship(back_populates="documents")  # noqa: F821
    sections: Mapped[list["DeviceDocumentSection"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="device_document", cascade="all, delete-orphan"
    )


class DeviceDocumentSection(Base):
    """Extracted structural section of an uploaded Device DOCX.

    Mirrors ``models.template.DocumentTemplate`` (the reference-document
    section table) but is keyed off ``device_documents`` instead of
    ``reference_documents``. Populated by
    ``services.device_document_parser.parse_and_store_sections`` right after
    upload (Phase 2.5). Embeddings are intentionally left out here - turning
    these rows into searchable RAG chunks (with a source_type marker so
    retrieval can tell reference and device content apart) is Phase 3.5.
    """

    __tablename__ = "device_document_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_name: Mapped[str] = mapped_column(String(255), nullable=False)
    section_type: Mapped[str] = mapped_column(String(50), nullable=False)
    heading_level: Mapped[int] = mapped_column(Integer, default=1)
    parent_section: Mapped[str] = mapped_column(String(255), nullable=True)
    section_order: Mapped[int] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    figure_refs: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped["DeviceDocument"] = relationship(back_populates="sections")
    
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_device_document_sections_doc_order", "document_id", "section_order"),
    )
