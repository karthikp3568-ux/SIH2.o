"""Append-only audit trail."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per consequential action. Never updated, never deleted in place."""

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(32))
    #: Dotted action code from core.enums.AuditAction.
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(48), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    #: Field-level before/after for data changes. Secrets are never recorded.
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),)
