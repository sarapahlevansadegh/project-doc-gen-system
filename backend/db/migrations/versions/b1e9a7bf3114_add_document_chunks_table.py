"""add_document_chunks_table

Revision ID: b1e9a7bf3114
Revises: 2bab55827fa9
Create Date: 2026-09-05 03:21:05.055457

Note: document_chunks table was already created by migration 2bab55827fa9
with the correct UUID foreign keys matching device_documents.id and
device_document_sections.id (both UUID primary keys). This revision is
kept as a no-op to preserve migration chain history.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1e9a7bf3114'
down_revision: Union[str, None] = '2bab55827fa9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass