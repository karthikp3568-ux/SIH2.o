"""OTP Generation, Hashing and Verification Service.

Enforces expiry, one-time use, attempt limits, resend cooldowns and secure hashing.
Supports Email and Phone SMS challenges with a clearly labelled development/demo mode.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User, VerificationChallenge, as_aware, utcnow
from ..security import hash_password

logger = logging.getLogger("app.otp")
settings = get_settings()

OTP_EXPIRY_MINUTES = 10
RESEND_COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5


def _hash_code(code: str, salt: str = "livelihood-otp-salt") -> str:
    return hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()


def generate_otp() -> str:
    """Generate a 6-digit cryptographically secure numeric OTP."""
    return str(secrets.randbelow(900000) + 100000)


def create_challenge(
    db: Session,
    destination: str,
    challenge_type: str,
    user: User | None = None,
) -> tuple[VerificationChallenge, str]:
    """Create or renew an OTP challenge for email or phone.

    Enforces 60-second cooldown from previous request to prevent abuse.
    Returns (challenge_record, raw_code).
    """
    destination_norm = destination.strip().lower()
    now = utcnow()

    # Check for active recent challenge within cooldown period
    candidates = db.execute(
        select(VerificationChallenge)
        .where(
            VerificationChallenge.destination == destination_norm,
            VerificationChallenge.challenge_type == challenge_type,
            VerificationChallenge.is_used == False,  # noqa: E712
        )
        .order_by(VerificationChallenge.created_at.desc())
    ).scalars().all()

    for candidate in candidates:
        resend_time = as_aware(candidate.resend_available_at)
        if resend_time and resend_time > now:
            remaining_seconds = max(1, int((resend_time - now).total_seconds()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining_seconds} seconds before requesting another verification code.",
            )

    code = generate_otp()
    code_hash = _hash_code(code)

    challenge = VerificationChallenge(
        user_id=user.id if user else None,
        destination=destination_norm,
        challenge_type=challenge_type,
        code_hash=code_hash,
        attempts=0,
        max_attempts=MAX_ATTEMPTS,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        resend_available_at=now + timedelta(seconds=RESEND_COOLDOWN_SECONDS),
        is_used=False,
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    logger.info(
        "[OTP] Challenge created type=%s dest=%s (expires_in=%dm)",
        challenge_type,
        destination_norm,
        OTP_EXPIRY_MINUTES,
    )
    return challenge, code


def verify_challenge(
    db: Session,
    destination: str,
    challenge_type: str,
    submitted_code: str,
) -> tuple[bool, str]:
    """Verify an OTP code against an active challenge.

    Returns (is_valid, message).
    """
    destination_norm = destination.strip().lower()
    now = utcnow()

    challenge = db.execute(
        select(VerificationChallenge)
        .where(
            VerificationChallenge.destination == destination_norm,
            VerificationChallenge.challenge_type == challenge_type,
            VerificationChallenge.is_used == False,  # noqa: E712
        )
        .order_by(VerificationChallenge.created_at.desc())
    ).scalars().first()

    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active verification code found for this destination. Please request a new code.",
        )

    expires = as_aware(challenge.expires_at)
    if expires and expires < now:
        challenge.is_used = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification code has expired. Please request a new code.",
        )

    if challenge.attempts >= challenge.max_attempts:
        challenge.is_used = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many invalid attempts. This code has been invalidated. Please request a new code.",
        )

    submitted_hash = _hash_code(submitted_code.strip())
    if submitted_hash != challenge.code_hash:
        challenge.attempts += 1
        db.commit()
        remaining = challenge.max_attempts - challenge.attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incorrect verification code. {remaining} attempt(s) remaining.",
        )

    # Valid code
    challenge.is_used = True
    challenge.verified_at = now

    # Update associated user status if present
    if challenge.user_id:
        user = db.get(User, challenge.user_id)
        if user:
            if challenge_type == "email":
                user.email_verified = True
            elif challenge_type == "phone":
                user.phone_verified = True
    else:
        # Match by email or phone directly
        user = None
        if challenge_type == "email":
            user = db.execute(select(User).where(User.email == destination_norm)).scalars().first()
            if user:
                user.email_verified = True
        elif challenge_type == "phone":
            user = db.execute(select(User).where(User.phone == destination_norm)).scalars().first()
            if user:
                user.phone_verified = True

    db.commit()
    logger.info("[OTP] Challenge verified type=%s dest=%s", challenge_type, destination_norm)
    return True, "Verification successful."


def reset_password_with_code(
    db: Session,
    email: str,
    code: str,
    new_password: str,
) -> bool:
    """Verify password_reset challenge and update user's password."""
    email_norm = email.strip().lower()
    user = db.execute(select(User).where(User.email == email_norm)).scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email address.",
        )

    verify_challenge(db, destination=email_norm, challenge_type="password_reset", submitted_code=code)
    user.password_hash = hash_password(new_password)
    user.token_version += 1  # Invalidate all prior sessions
    db.commit()
    logger.info("[OTP] Password successfully reset for user email=%s", email_norm)
    return True
