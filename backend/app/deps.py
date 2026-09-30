"""Shared FastAPI dependencies: authentication, RBAC and ownership checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .core.enums import Role
from .db import get_db
from .models import BeneficiaryProfile, User
from .security import TOKEN_TYPE_ACCESS, decode_token

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_ERROR
    payload = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    if payload is None:
        raise CREDENTIALS_ERROR

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    # Token version lets an admin (or a password change) revoke live tokens.
    if payload.get("ver") != user.token_version:
        raise CREDENTIALS_ERROR

    # The role always comes from the database row, never from the token claim,
    # so a stale or tampered token cannot escalate privileges.
    request.state.user_id = user.id
    request.state.user_role = user.role
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_roles(*roles: str) -> Callable[[User], User]:
    """Dependency factory enforcing that the caller holds one of `roles`."""
    allowed = {str(r) for r in roles}

    def _dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return _dependency


require_admin = require_roles(Role.ADMIN)
require_staff = require_roles(Role.ADMIN, Role.COUNSELLOR)
require_provider = require_roles(Role.ADMIN, Role.PROVIDER)

AdminUser = Annotated[User, Depends(require_admin)]
StaffUser = Annotated[User, Depends(require_staff)]
ProviderUser = Annotated[User, Depends(require_provider)]


def get_current_beneficiary(user: CurrentUser, db: DbSession) -> BeneficiaryProfile:
    """The calling user's own beneficiary profile, created lazily if missing."""
    profile = db.query(BeneficiaryProfile).filter_by(user_id=user.id).one_or_none()
    if profile is None:
        if user.role != Role.BENEFICIARY:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This account does not have a beneficiary profile.",
            )
        profile = BeneficiaryProfile(
            user_id=user.id,
            display_name=user.full_name,
            preferred_language=user.preferred_language,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


CurrentBeneficiary = Annotated[BeneficiaryProfile, Depends(get_current_beneficiary)]


def resolve_beneficiary_for_actor(
    beneficiary_id: str, user: User, db: Session
) -> BeneficiaryProfile:
    """Fetch a beneficiary, enforcing that the actor is allowed to see it.

    Staff may read anyone; a beneficiary may only read themselves. The 404 for a
    non-owner is deliberate - it does not reveal whether the id exists.
    """
    profile = db.get(BeneficiaryProfile, beneficiary_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")
    if user.role in {Role.ADMIN, Role.COUNSELLOR}:
        return profile
    if profile.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")
    return profile
