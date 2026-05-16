"""phase 3: memory enhancements

Revision ID: 0003_memory_fields
Revises: 0002_rag_fields
Create Date: 2026-05-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003_memory_fields"
down_revision: Union[str, None] = "0002_rag_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to existing memories table
    op.add_column("memories", sa.Column("source_message_id", UUID(as_uuid=True)))

    # Stricter type check (drop if existed via CHECK in initial)
    op.execute(
        """
        ALTER TABLE memories
        DROP CONSTRAINT IF EXISTS ck_memories_type
        """
    )
    op.create_check_constraint(
        "ck_memories_type",
        "memories",
        "memory_type IN ('factual','preference','context','episodic')",
    )

    # Composite index for filtered list (already partial via initial — keep)
    op.create_index(
        "ix_memories_user_type",
        "memories",
        ["tenant_id", "user_id", "memory_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_type", "memories")
    op.drop_constraint("ck_memories_type", "memories")
    op.drop_column("memories", "source_message_id")
