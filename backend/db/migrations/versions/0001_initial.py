import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# Initial schema for DocGen system.
# Creates pgvector extension, core tables (devices, device_specs,
# device_alarms, serial_commands, generated_documents) and the
# RAG tables (reference_documents, document_templates) with the
# M1 extensions: versioning, embedding metadata and section_type.

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("document_code", sa.String(50), nullable=True),
        sa.Column("safety_class", sa.String(10), server_default="B"),
        sa.Column("driver_version", sa.String(50), nullable=True),
        sa.Column("gui_version", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "device_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("spec_key", sa.String(255), nullable=False),
        sa.Column("spec_value", sa.Text, nullable=False),
        sa.Column("spec_unit", sa.String(50), nullable=True),
    )

    op.create_table(
        "device_alarms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("condition", sa.Text, nullable=False),
        sa.Column("text_shown", sa.Text, nullable=True),
        sa.Column("indicator_light", sa.String(100), nullable=True),
        sa.Column("indicator_sound", sa.Boolean, server_default=sa.false()),
        sa.Column("required_action", sa.Text, nullable=True),
        sa.Column("alarm_order", sa.Integer, nullable=True),
    )

    op.create_table(
        "serial_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("direction", sa.String(20), nullable=True),
        sa.Column("command_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("laser_a_mapping", sa.String(100), nullable=True),
        sa.Column("laser_b_mapping", sa.String(100), nullable=True),
        sa.Column("command_order", sa.Integer, nullable=True),
    )

    op.create_table(
        "generated_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("generation_log", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "reference_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("template_name", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=True),
        sa.Column("section_count", sa.Integer, server_default="0"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("embedding_dimension", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "document_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_name", sa.String(255), nullable=False),
        sa.Column(
            "source_doc_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reference_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_name", sa.String(255), nullable=False),
        sa.Column("section_type", sa.String(50), server_default="TEXT"),
        sa.Column("heading_level", sa.Integer, server_default="1"),
        sa.Column("parent_section", sa.String(255), nullable=True),
        sa.Column("section_order", sa.Integer, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("figure_refs", postgresql.JSONB, server_default="[]"),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("embedding_dimension", sa.Integer, nullable=True),
        sa.Column("meta_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_index(
        "ix_document_templates_source_order",
        "document_templates",
        ["source_doc_id", "section_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_templates_source_order", table_name="document_templates")
    op.drop_table("document_templates")
    op.drop_table("reference_documents")
    op.drop_table("generated_documents")
    op.drop_table("serial_commands")
    op.drop_table("device_alarms")
    op.drop_table("device_specs")
    op.drop_table("devices")
