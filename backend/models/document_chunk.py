import uuid
from datetime import datetime

from core.database import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class DocumentChunk(Base):
    """RAG-ready text chunk with embedding, derived from a device document section."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device_document_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    section: Mapped["DeviceDocumentSection"] = relationship(back_populates="chunks")  # noqa: F821
    device_document: Mapped["DeviceDocument"] = relationship(back_populates="chunks")  # noqa: F821