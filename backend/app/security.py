"""Password hashing and JWT issuance/verification.

Password hashing uses PBKDF2-HMAC-SHA256 from the standard library at 600,000
iterations (the OWASP 2023 recommendation for PBKDF2-SHA256). This avoids a
native build dependency while remaining a genuinely accepted KDF. If you later
add `argon2-cffi` or `bcrypt`, `verify_password` can be extended to
transparently re-hash legacy digests on next successful login.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError

from .config import get_settings

settings = get_settings()

_PBKDF2_ITERATIONS = 600_000
_PBKDF2_ALGO = "pbkdf2_sha256"
_SALT_BYTES = 16

JWT_ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Return `pbkdf2_sha256$iterations$salt$hash`."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification. Returns False on any malformed digest."""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(candidate, expected)


_PASSWORD_RULES = (
    (re.compile(r"[a-z]"), "a lowercase letter"),
    (re.compile(r"[A-Z]"), "an uppercase letter"),
    (re.compile(r"[0-9]"), "a digit"),
)


def validate_password_strength(password: str) -> list[str]:
    """Return a list of human-readable problems; empty means acceptable."""
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"must be at least {settings.password_min_length} characters")
    for pattern, description in _PASSWORD_RULES:
        if not pattern.search(password):
            problems.append(f"must contain {description}")
    if password.lower() in {"password", "12345678", "qwerty123", "admin123"}:
        problems.append("is too common")
    return problems


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def _create_token(
    subject: str, token_type: str, expires_delta: timedelta, claims: dict[str, Any] | None = None
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: str, role: str, token_version: int) -> str:
    return _create_token(
        user_id,
        TOKEN_TYPE_ACCESS,
        timedelta(minutes=settings.access_token_ttl_minutes),
        {"role": role, "ver": token_version},
    )


def create_refresh_token(user_id: str, token_version: int) -> str:
    return _create_token(
        user_id,
        TOKEN_TYPE_REFRESH,
        timedelta(days=settings.refresh_token_ttl_days),
        {"ver": token_version},
    )


def decode_token(token: str, expected_type: str = TOKEN_TYPE_ACCESS) -> dict[str, Any] | None:
    """Return the payload, or None if the token is invalid/expired/wrong type."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except InvalidTokenError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
