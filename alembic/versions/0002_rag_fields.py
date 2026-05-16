"""phase 2: document storage fields

Revision ID: 0002_rag_fields
Revises: 0001_initial
Create Date: 2026-05-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_rag_fields"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("storage_path", sa.String(1000)))
    op.add_column("documents", sa.Column("file_type", sa.String(20)))
    op.add_column("documents", sa.Column("file_hash", sa.String(64), index=True))
    op.add_column("documents", sa.Column("metadata", sa.dialects.postgresql.JSONB))
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])

    # Add chunk_metadata column rename — actual column was named 'metadata' originally;
    # we keep it. Add updated_at to chunks if missing.
    op.execute(
        """
        ALTER TABLE chunks
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()
        """
    )


def downgrade() -> None:
    op.drop_index("ix_documents_file_hash", "documents")
    op.drop_column("documents", "metadata")
    op.drop_column("documents", "file_hash")
    op.drop_column("documents", "file_type")
    op.drop_column("documents", "storage_path")
