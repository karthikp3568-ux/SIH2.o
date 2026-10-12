"""Authentication, consent and self-service account endpoints."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from ..config import get_settings
from ..core.enums import AuditAction, Role
from ..core.rate_limit import auth_rate_limit, default_rate_limit, register_rate_limit
from ..deps import CurrentUser, DbSession
from ..models import BeneficiaryProfile, Consent, User, as_aware, utcnow
from ..schemas.auth import (
    AuthResponse,
    ConsentIn,
    ConsentOut,
    LoginRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    SendOtpRequest,
    SendOtpResponse,
    TokenPair,
    UserOut,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from ..security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from ..services import audit
from ..services import otp as otp_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

#: Lock an account briefly after repeated failures, to blunt credential stuffing.
MAX_FAILED_LOGINS = 8
LOCKOUT_MINUTES = 15


def _tokens_for(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, user.role, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
        expires_in_minutes=settings.access_token_ttl_minutes,
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_rate_limit)],
)
def register(payload: RegisterRequest, request: Request, db: DbSession) -> AuthResponse:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=str(payload.email).lower(),
        full_name=payload.full_name,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        # The role is set here, never read from the request body.
        role=Role.BENEFICIARY,
        preferred_language=str(payload.preferred_language),
        email_verified=False,
        phone_verified=False,
    )
    db.add(user)
    db.flush()

    db.add(
        BeneficiaryProfile(
            user_id=user.id,
            display_name=payload.full_name,
            preferred_language=str(payload.preferred_language),
        )
    )

    now = utcnow()
    for purpose, granted in (
        ("profile_processing", payload.consent_profile_processing),
        ("voice_processing", payload.consent_voice_processing),
        ("location_processing", payload.consent_location_processing),
        ("outcome_tracking", payload.consent_outcome_tracking),
    ):
        db.add(
            Consent(
                user_id=user.id,
                purpose=purpose,
                granted=granted,
                granted_at=now if granted else None,
            )
        )

    # Generate initial email verification challenge
    dev_code = None
    try:
        _, raw_code = otp_service.create_challenge(
            db, destination=user.email, challenge_type="email", user=user
        )
        if settings.demo_mode or settings.environment in {"development", "test", "dev"}:
            dev_code = raw_code
    except Exception:
        pass

    audit.record(
        db,
        action=AuditAction.REGISTER,
        actor=user,
        entity_type="user",
        entity_id=user.id,
        new_value={"email": user.email, "role": user.role},
        summary="New beneficiary account created",
        request=request,
    )
    db.commit()
    db.refresh(user)
    return AuthResponse(
        user=UserOut.model_validate(user),
        tokens=_tokens_for(user),
        otp_sent=True,
        dev_otp=dev_code,
    )


@router.post("/otp/send", response_model=SendOtpResponse, dependencies=[Depends(auth_rate_limit)])
def send_otp(payload: SendOtpRequest, db: DbSession) -> SendOtpResponse:
    """Generate and send an OTP code for email, phone or password reset."""
    destination = payload.destination.strip().lower()
    user = None
    if payload.challenge_type == "email":
        user = db.execute(select(User).where(User.email == destination)).scalar_one_or_none()
    elif payload.challenge_type == "phone":
        user = db.execute(select(User).where(User.phone == destination)).scalar_one_or_none()

    _, raw_code = otp_service.create_challenge(
        db, destination=destination, challenge_type=payload.challenge_type, user=user
    )

    is_dev = bool(settings.demo_mode or settings.environment in {"development", "test", "dev"})
    dev_code = raw_code if is_dev else None

    return SendOtpResponse(
        message=f"Verification code sent to {payload.destination}",
        destination=payload.destination,
        challenge_type=payload.challenge_type,
        resend_in_seconds=otp_service.RESEND_COOLDOWN_SECONDS,
        expires_in_minutes=otp_service.OTP_EXPIRY_MINUTES,
        dev_code=dev_code,
        is_dev_mode=is_dev,
    )


@router.post("/otp/verify", response_model=VerifyOtpResponse, dependencies=[Depends(auth_rate_limit)])
def verify_otp(payload: VerifyOtpRequest, db: DbSession) -> VerifyOtpResponse:
    """Verify an OTP code for email, phone, or password reset."""
    success, message = otp_service.verify_challenge(
        db,
        destination=payload.destination,
        challenge_type=payload.challenge_type,
        submitted_code=payload.code,
    )

    destination_norm = payload.destination.strip().lower()
    user = db.execute(
        select(User).where(
            (User.email == destination_norm) | (User.phone == destination_norm)
        )
    ).scalar_one_or_none()

    return VerifyOtpResponse(
        verified=success,
        message=message,
        email_verified=bool(user.email_verified if user else payload.challenge_type == "email"),
        phone_verified=bool(user.phone_verified if user else payload.challenge_type == "phone"),
    )


@router.post("/password-reset/request", response_model=SendOtpResponse, dependencies=[Depends(auth_rate_limit)])
def request_password_reset(payload: SendOtpRequest, db: DbSession) -> SendOtpResponse:
    """Send a password reset OTP to an account email."""
    email_norm = payload.destination.strip().lower()
    user = db.execute(select(User).where(User.email == email_norm)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account registered with this email address.",
        )

    _, raw_code = otp_service.create_challenge(
        db, destination=email_norm, challenge_type="password_reset", user=user
    )

    is_dev = bool(settings.demo_mode or settings.environment in {"development", "test", "dev"})
    return SendOtpResponse(
        message=f"Password reset code sent to {email_norm}",
        destination=email_norm,
        challenge_type="password_reset",
        resend_in_seconds=otp_service.RESEND_COOLDOWN_SECONDS,
        expires_in_minutes=otp_service.OTP_EXPIRY_MINUTES,
        dev_code=raw_code if is_dev else None,
        is_dev_mode=is_dev,
    )


@router.post("/password-reset/confirm", dependencies=[Depends(auth_rate_limit)])
def confirm_password_reset(payload: PasswordResetRequest, request: Request, db: DbSession) -> dict[str, str]:
    """Verify code and update the account password."""
    otp_service.reset_password_with_code(
        db, email=payload.email, code=payload.code, new_password=payload.new_password
    )
    user = db.execute(select(User).where(User.email == payload.email.strip().lower())).scalar_one_or_none()
    if user:
        audit.record(
            db,
            action=AuditAction.PROFILE_UPDATED,
            actor=user,
            entity_type="user",
            entity_id=user.id,
            summary="Password reset successfully via OTP",
            request=request,
        )
    return {"message": "Password has been successfully updated. You may now sign in."}


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(auth_rate_limit)])
def login(payload: LoginRequest, request: Request, db: DbSession) -> AuthResponse:
    user = db.execute(
        select(User).where(User.email == str(payload.email).lower())
    ).scalar_one_or_none()

    # Identical error for "no such user" and "wrong password" - not leaking
    # which emails are registered.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password."
    )

    if user is None:
        audit.record(
            db,
            action=AuditAction.LOGIN_FAILURE,
            entity_type="user",
            new_value={"email": str(payload.email).lower(), "reason": "unknown_account"},
            request=request,
            commit=True,
        )
        raise invalid

    locked_until = as_aware(user.locked_until)
    if locked_until is not None and locked_until > utcnow():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again shortly.",
        )

    if not user.is_active or not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        audit.record(
            db,
            action=AuditAction.LOGIN_FAILURE,
            actor=user,
            entity_type="user",
            entity_id=user.id,
            new_value={"reason": "bad_password" if user.is_active else "inactive"},
            request=request,
        )
        db.commit()
        raise invalid

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit.record(
        db,
        action=AuditAction.LOGIN_SUCCESS,
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary="Signed in",
        request=request,
    )
    db.commit()
    db.refresh(user)
    return AuthResponse(user=UserOut.model_validate(user), tokens=_tokens_for(user))


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(default_rate_limit)])
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    claims = decode_token(payload.refresh_token, TOKEN_TYPE_REFRESH)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token."
        )
    user = db.get(User, claims.get("sub"))
    if user is None or not user.is_active or claims.get("ver") != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token."
        )
    return _tokens_for(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, db: DbSession) -> None:
    """Invalidate every token issued to this account so far."""
    user.token_version += 1
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/consents", response_model=list[ConsentOut])
def list_consents(user: CurrentUser, db: DbSession) -> list[ConsentOut]:
    rows = db.execute(select(Consent).where(Consent.user_id == user.id)).scalars().all()
    return [
        ConsentOut(
            purpose=c.purpose,
            granted=c.granted,
            granted_at=c.granted_at.isoformat() if c.granted_at else None,
            withdrawn_at=c.withdrawn_at.isoformat() if c.withdrawn_at else None,
            policy_version=c.policy_version,
        )
        for c in rows
    ]


@router.put("/consents", response_model=ConsentOut)
def set_consent(
    payload: ConsentIn, user: CurrentUser, request: Request, db: DbSession
) -> ConsentOut:
    consent = db.execute(
        select(Consent).where(Consent.user_id == user.id, Consent.purpose == payload.purpose)
    ).scalar_one_or_none()
    if consent is None:
        consent = Consent(user_id=user.id, purpose=payload.purpose, granted=False)
        db.add(consent)

    consent.granted = payload.granted
    if payload.granted:
        consent.granted_at = utcnow()
        consent.withdrawn_at = None
    else:
        consent.withdrawn_at = utcnow()

    audit.record(
        db,
        action=AuditAction.CONSENT_GRANTED if payload.granted else AuditAction.CONSENT_WITHDRAWN,
        actor=user,
        entity_type="consent",
        entity_id=consent.id,
        new_value={"purpose": payload.purpose, "granted": payload.granted},
        request=request,
    )
    db.commit()
    db.refresh(consent)
    return ConsentOut(
        purpose=consent.purpose,
        granted=consent.granted,
        granted_at=consent.granted_at.isoformat() if consent.granted_at else None,
        withdrawn_at=consent.withdrawn_at.isoformat() if consent.withdrawn_at else None,
        policy_version=consent.policy_version,
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_data(user: CurrentUser, request: Request, db: DbSession) -> None:
    """Erase the account and everything that cascades from it.

    Audit rows are retained with the actor de-linked (ON DELETE SET NULL), so
    the record that an action happened survives without keeping the person's
    identity attached to it.
    """
    audit.record(
        db,
        action=AuditAction.DATA_DELETED,
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary="Account and associated data deleted at the user's request",
        request=request,
    )
    db.delete(user)
    db.commit()
