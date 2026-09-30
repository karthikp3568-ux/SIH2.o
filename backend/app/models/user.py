"""Accounts, roles and consent."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import Role
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Role is assigned server side only. Registration endpoints never read it
    # from the request body - see app/api/auth.py.
    role: Mapped[str] = mapped_column(String(32), default=Role.BENEFICIARY, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bump to invalidate every previously issued token for this user.
    token_version: Mapped[int] = mapped_column(default=0, nullable=False)

    beneficiary: Mapped["BeneficiaryProfile | None"] = relationship(  # noqa: F821
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    consents: Mapped[list["Consent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)


class Consent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Explicit, purpose-scoped consent records.

    One row per (user, purpose). Withdrawal sets `granted=False` and stamps
    `withdrawn_at`; the row is retained as evidence of the decision.
    """

    __tablename__ = "consents"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # voice_processing | profile_processing | location_processing | outcome_tracking
    purpose: Mapped[str] = mapped_column(String(48), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="consents")

    __table_args__ = (Index("ix_consent_user_purpose", "user_id", "purpose", unique=True),)
