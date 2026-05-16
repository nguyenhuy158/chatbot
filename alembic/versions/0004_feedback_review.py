"""phase 6: feedback review fields

Revision ID: 0004_feedback_review
Revises: 0003_memory_fields
Create Date: 2026-05-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0004_feedback_review"
down_revision: Union[str, None] = "0003_memory_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("reviewed_by", UUID(as_uuid=True)))
    op.add_column("feedback", sa.Column("reviewed_action", sa.String(50)))
    op.add_column("feedback", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_feedback_pending", "feedback", ["tenant_id", "rating", "reviewed_action"])


def downgrade() -> None:
    op.drop_index("ix_feedback_pending", "feedback")
    op.drop_column("feedback", "updated_at")
    op.drop_column("feedback", "reviewed_action")
    op.drop_column("feedback", "reviewed_by")
