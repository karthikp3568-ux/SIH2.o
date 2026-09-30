"""Test fixtures.

Environment variables are set before any application module is imported, so the
tests run against a throwaway SQLite file and never touch a developer database.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP_DIR = Path(tempfile.mkdtemp(prefix="livelihood-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}",
        "SEED_ON_STARTUP": "false",
        "DEMO_MODE": "true",
        "RATE_LIMIT_ENABLED": "false",
        "SECRET_KEY": "test-secret-key-not-used-anywhere-else-0123456789",
        "PROFILE_EXTRACTOR": "rule_based",
        "LLM_PROVIDER": "none",
        "EMBEDDING_PROVIDER": "local_hashing",
        "SPEECH_PROVIDER": "mock",
        "STORE_RAW_AUDIO": "false",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, BeneficiaryProfile, User  # noqa: E402
from app.seed.seed_data import DEMO_LOCATION, seed_database  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def ravi(db: Session) -> BeneficiaryProfile:
    """Ravi with the profile the problem statement describes, freshly built."""
    from sqlalchemy import select

    from app.config import get_settings
    from app.services import profile_service

    settings = get_settings()
    user = db.execute(
        select(User).where(User.email == settings.demo_beneficiary_email)
    ).scalar_one()
    profile = db.execute(
        select(BeneficiaryProfile).where(BeneficiaryProfile.user_id == user.id)
    ).scalar_one()

    for row in list(profile.locations):
        db.delete(row)
    db.flush()
    profile_service.upsert_location(db, profile, DEMO_LOCATION)

    draft = {
        "education": {"value": "class_10", "confidence": 0.9, "evidence": "test fixture"},
        "occupations": [
            {"value": "Agriculture / farm work", "confidence": 0.9, "evidence": "test fixture"}
        ],
        "skills": [
            {
                "code": "pump_repair",
                "name": "Pump repair",
                "raw_label": "pump repair",
                "proficiency": "intermediate",
                "confidence": "high",
                "source": "self_reported",
                "verification_status": "self_declared",
                "years_experience": 5,
                "evidence": "test fixture",
                "is_category": False,
            },
            {
                "code": "farm_machinery_maintenance",
                "name": "Farm machinery maintenance",
                "raw_label": "farm machinery maintenance",
                "proficiency": "intermediate",
                "confidence": "high",
                "source": "self_reported",
                "verification_status": "self_declared",
                "years_experience": 5,
                "evidence": "test fixture",
                "is_category": False,
            },
        ],
        "interests": [{"value": "mechanical", "confidence": 0.8, "evidence": "test fixture"}],
        "goals": [
            {"value": "self_employment", "confidence": 0.9, "evidence": "test fixture"},
            {"value": "higher_income", "confidence": 0.9, "evidence": "test fixture"},
        ],
        "constraints": [],
        "mobility": {"value": "low", "confidence": 0.9, "evidence": "test fixture"},
        "age": {"value": 29, "confidence": 0.9, "evidence": "test fixture"},
        "location": DEMO_LOCATION,
    }
    profile_service.apply_draft(db, profile, draft)
    db.refresh(profile)
    return profile


@pytest.fixture
def admin_token(client: TestClient) -> str:
    from app.config import get_settings

    settings = get_settings()
    response = client.post(
        "/api/auth/login",
        json={"email": settings.demo_admin_email, "password": settings.demo_admin_password},
    )
    assert response.status_code == 200, response.text
    return response.json()["tokens"]["access_token"]


@pytest.fixture
def beneficiary_token(client: TestClient) -> str:
    from app.config import get_settings

    settings = get_settings()
    response = client.post(
        "/api/auth/login",
        json={
            "email": settings.demo_beneficiary_email,
            "password": settings.demo_beneficiary_password,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["tokens"]["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
