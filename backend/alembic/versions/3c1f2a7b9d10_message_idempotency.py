"""message idempotency: client_message_id + response_snapshot

Revision ID: 3c1f2a7b9d10
Revises: 09dcb7253a5d
Create Date: 2026-10-04 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "3c1f2a7b9d10"
down_revision: str | None = "09dcb7253a5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("client_message_id", sa.String(length=64), nullable=True))
    op.add_column("conversation_messages", sa.Column("response_snapshot", sa.JSON(), nullable=True))
    op.create_index(
        "ix_message_conversation_client_id",
        "conversation_messages",
        ["conversation_id", "client_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_message_conversation_client_id", table_name="conversation_messages")
    op.drop_column("conversation_messages", "response_snapshot")
    op.drop_column("conversation_messages", "client_message_id")
