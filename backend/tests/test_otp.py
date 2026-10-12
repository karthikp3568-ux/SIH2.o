"""Tests for OTP challenge creation, rate limiting, expiry, and verification."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, VerificationChallenge
from app.services import otp as otp_service


class TestOtpService:
    def test_create_and_verify_email_otp(self, db: Session) -> None:
        email = "test-beneficiary@example.com"
        challenge, code = otp_service.create_challenge(db, destination=email, challenge_type="email")
        assert challenge is not None
        assert len(code) == 6
        assert code.isdigit()
        assert challenge.attempts == 0
        assert not challenge.is_used

        # Incorrect code increments attempts
        with pytest.raises(HTTPException) as exc_info:
            otp_service.verify_challenge(db, destination=email, challenge_type="email", submitted_code="000000")
        assert exc_info.value.status_code == 400
        assert "attempt(s) remaining" in exc_info.value.detail

        # Correct code succeeds
        success, msg = otp_service.verify_challenge(db, destination=email, challenge_type="email", submitted_code=code)
        assert success is True
        assert "successful" in msg.lower()

        # Re-using code fails
        with pytest.raises(HTTPException):
            otp_service.verify_challenge(db, destination=email, challenge_type="email", submitted_code=code)

    def test_cooldown_prevents_immediate_resend(self, db: Session) -> None:
        email = "cooldown-test@example.com"
        otp_service.create_challenge(db, destination=email, challenge_type="email")
        with pytest.raises(HTTPException) as exc_info:
            otp_service.create_challenge(db, destination=email, challenge_type="email")
        assert exc_info.value.status_code == 429
        assert "Please wait" in exc_info.value.detail


class TestOtpApi:
    def test_registration_returns_otp_in_dev_mode(self, client: TestClient) -> None:
        payload = {
            "full_name": "Kavitha Gowda",
            "email": "kavitha.gowda@example.com",
            "password": "Password@123",
            "phone": "+919876543210",
            "preferred_language": "kn",
            "consent_profile_processing": True,
            "consent_voice_processing": True,
        }
        res = client.post("/api/auth/register", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["user"]["email"] == "kavitha.gowda@example.com"
        assert data["user"]["preferred_language"] == "kn"
        assert data["otp_sent"] is True
        assert data["dev_otp"] is not None

        # Verify using OTP endpoint
        verify_res = client.post(
            "/api/auth/otp/verify",
            json={
                "destination": "kavitha.gowda@example.com",
                "challenge_type": "email",
                "code": data["dev_otp"],
            },
        )
        assert verify_res.status_code == 200
        assert verify_res.json()["verified"] is True
        assert verify_res.json()["email_verified"] is True
