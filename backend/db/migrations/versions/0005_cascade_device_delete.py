"""Cascade delete generated_documents when device is removed."""
from alembic import op

revision = "0005_cascade_device_delete"
down_revision = "0004_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("generated_documents_device_id_fkey", "generated_documents", type_="foreignkey")
    op.create_foreign_key(
        "generated_documents_device_id_fkey",
        "generated_documents",
        "devices",
        ["device_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("generated_documents_device_id_fkey", "generated_documents", type_="foreignkey")
    op.create_foreign_key(
        "generated_documents_device_id_fkey",
        "generated_documents",
        "devices",
        ["device_id"],
        ["id"],
    )
