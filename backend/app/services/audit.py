"""Audit logging.

One helper, used everywhere, so that every consequential action is recorded the
same way. Values are shallow-copied dicts of primitives - password hashes,
tokens and raw audio references are never written here.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, User

#: Never recorded, even if present on an object being diffed.
_REDACTED_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "audio_reference",
}


def _sanitise(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if k.lower() in _REDACTED_KEYS else _sanitise(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitise(v) for v in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    summary: str | None = None,
    request: Request | None = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=str(action),
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=_sanitise(old_value) if old_value is not None else None,
        new_value=_sanitise(new_value) if new_value is not None else None,
        summary=summary,
        ip_address=request.client.host if request and request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:300] if request else None,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def model_snapshot(instance: Any, fields: list[str]) -> dict:
    """Shallow dict of selected fields, for before/after diffs."""
    return {field: _sanitise(getattr(instance, field, None)) for field in fields}


def diff(before: dict, after: dict) -> tuple[dict, dict]:
    """Return only the fields that actually changed."""
    changed_before, changed_after = {}, {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            changed_before[key] = before.get(key)
            changed_after[key] = after.get(key)
    return changed_before, changed_after


def list_for_entity(db: Session, entity_type: str, entity_id: str, limit: int = 50) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
