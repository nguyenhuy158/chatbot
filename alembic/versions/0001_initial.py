"""initial schema with pgvector

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("name", sa.String(255)),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("sso_provider", sa.String(50)),
        sa.Column("sso_subject", sa.String(255)),
        sa.Column("preferences", JSONB, server_default="{}"),
        sa.Column("reputation_score", sa.Integer, server_default="100"),
        sa.Column("banned_until", sa.DateTime(timezone=True)),
        sa.Column("last_active_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('internal','external','admin')", name="ck_users_role"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    # conversations
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("title", sa.String(255)),
        sa.Column("channel", sa.String(20), server_default="web"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # messages
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tool_calls", JSONB),
        sa.Column("citations", JSONB),
        sa.Column("tokens_input", sa.Integer),
        sa.Column("tokens_output", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("model", sa.String(100)),
        sa.Column("cached", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('user','assistant','tool','system')", name="ck_messages_role"),
    )
    op.create_index("ix_messages_conv_created", "messages", ["conversation_id", "created_at"])

    # feedback
    op.create_table(
        "feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("rating", sa.SmallInteger, nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("rating IN (-1, 1)", name="ck_feedback_rating"),
    )

    # documents
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("collection", sa.String(100), nullable=False, index=True),
        sa.Column("title", sa.String(500)),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("owner_email", sa.String(255)),
        sa.Column("acl", JSONB),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="approved"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('draft','approved','archived')", name="ck_documents_status"),
    )

    # chunks (pgvector)
    op.execute(
        """
        CREATE TABLE chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL,
            document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            embedding VECTOR(768),
            chunk_index INTEGER,
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX ON chunks (document_id);
        CREATE INDEX ON chunks (tenant_id);
        """
    )

    # memories (pgvector)
    op.execute(
        """
        CREATE TABLE memories (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR(768),
            metadata JSONB,
            pinned BOOLEAN DEFAULT FALSE,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX ON memories (tenant_id, user_id, memory_type);
        """
    )

    # tool_audit
    op.create_table(
        "tool_audit",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), index=True),
        sa.Column("tool_name", sa.String(100)),
        sa.Column("input", JSONB),
        sa.Column("output", JSONB),
        sa.Column("success", sa.Boolean),
        sa.Column("error", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # moderation_events
    op.create_table(
        "moderation_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), index=True),
        sa.Column("event_type", sa.String(50)),
        sa.Column("severity", sa.String(20)),
        sa.Column("content_snippet", sa.Text),
        sa.Column("action_taken", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("actor_id", UUID(as_uuid=True)),
        sa.Column("action", sa.String(100)),
        sa.Column("target_type", sa.String(100)),
        sa.Column("target_id", UUID(as_uuid=True)),
        sa.Column("metadata", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("moderation_events")
    op.drop_table("tool_audit")
    op.execute("DROP TABLE IF EXISTS memories CASCADE")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.drop_table("documents")
    op.drop_table("feedback")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
