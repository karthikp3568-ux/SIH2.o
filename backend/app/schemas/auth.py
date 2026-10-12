"""Authentication schemas.

Note what is absent: `role`. Registration never accepts a role from the client;
the server assigns `beneficiary`. Privileged accounts are created by an existing
admin through /api/admin/users.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..core.enums import Language, Role
from ..security import validate_password_strength


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, pattern=r"^[0-9+\-\s]{6,20}$")
    preferred_language: Language = Language.EN
    #: Explicit, purpose-scoped consent. Registration is refused without it.
    consent_profile_processing: bool
    consent_voice_processing: bool = False
    consent_location_processing: bool = False
    consent_outcome_tracking: bool = False

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("Password " + "; ".join(problems))
        return value

    @field_validator("consent_profile_processing")
    @classmethod
    def _require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "Consent to process your profile is required to create an account."
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    phone: str | None = None
    role: Role
    preferred_language: str
    is_active: bool
    email_verified: bool = False
    phone_verified: bool = False


class SendOtpRequest(BaseModel):
    destination: str = Field(min_length=3, max_length=255)
    challenge_type: str = Field(pattern="^(email|phone|password_reset)$")


class SendOtpResponse(BaseModel):
    message: str
    destination: str
    challenge_type: str
    resend_in_seconds: int
    expires_in_minutes: int
    dev_code: str | None = None
    is_dev_mode: bool = False


class VerifyOtpRequest(BaseModel):
    destination: str = Field(min_length=3, max_length=255)
    challenge_type: str = Field(pattern="^(email|phone|password_reset)$")
    code: str = Field(min_length=4, max_length=10)


class VerifyOtpResponse(BaseModel):
    verified: bool
    message: str
    email_verified: bool = False
    phone_verified: bool = False


class PasswordResetRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong_enough(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("Password " + "; ".join(problems))
        return value


class AuthResponse(BaseModel):
    user: UserOut
    tokens: TokenPair
    otp_sent: bool = False
    dev_otp: str | None = None


class ConsentIn(BaseModel):
    purpose: str = Field(
        pattern="^(voice_processing|profile_processing|location_processing|outcome_tracking)$"
    )
    granted: bool


class ConsentOut(BaseModel):
    purpose: str
    granted: bool
    granted_at: str | None = None
    withdrawn_at: str | None = None
    policy_version: str


class CreateUserRequest(BaseModel):
    """Admin-only. This is the single place a privileged role can be assigned."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: Role
    preferred_language: Language = Language.EN

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("Password " + "; ".join(problems))
        return value

