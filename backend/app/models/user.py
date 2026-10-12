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
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    verification_challenges: Mapped[list["VerificationChallenge"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)


class VerificationChallenge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Secure, expiring OTP challenge for email, SMS or password recovery."""

    __tablename__ = "verification_challenges"

    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    destination: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # email | phone | password_reset
    challenge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resend_available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="verification_challenges")

    __table_args__ = (
        Index("ix_challenges_dest_type", "destination", "challenge_type"),
    )


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
