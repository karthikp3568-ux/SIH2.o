"""FastAPI application entry point."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from . import __version__
from .api import api_router
from .config import get_settings
from .db import SessionLocal, engine
from .seed.seed_data import create_all_tables, seed_database
from .services.semantic_understanding import warm_up

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("livelihood_navigator")

settings = get_settings()

DESCRIPTION = """
AI-Driven Multilingual Livelihood Navigator - backend API.

The journey this API implements:

**Phase 1 - Understand**: voice or text in a regional language, language
identification, code-switch handling, adaptive slot-filling conversation.

**Phase 2 - Profile & Reason**: structured profile extraction, skill
normalisation against a canonical taxonomy, skill-graph construction and
skill-gap analysis against NSQF-shaped qualification records.

**Phase 3 - Match & Personalise**: grounded hybrid retrieval (vector + keyword +
structured metadata filters), hard eligibility/availability gates, a weighted
nine-factor ranking engine, and an explanation derived from the computed factors.

**Phase 4 - Measure & Learn**: pathway selection, outcome lifecycle tracking and
structured feedback.

Design commitments visible in this API:
* Recommendations are always rows in `opportunities` that passed every hard
  filter. Nothing is generated. When nothing qualifies, `/recommendations`
  returns a no-match response with a prerequisite pathway instead.
* Self-reported and verified skills are distinct values throughout.
* Expired, inactive, unverified-for-a-year listings and retired qualification
  standards are excluded, and the exclusion reason is retrievable.
* `/system/providers` states exactly which integrations are live and which are
  interface-only.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_production_safe()
    logger.info("Starting %s v%s (%s)", settings.app_name, __version__, settings.environment)

    create_all_tables(engine)
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            summary = seed_database(db)
            logger.info("Seed summary: %s", summary)
        except SQLAlchemyError:
            logger.exception("Seeding failed; the app will start with whatever data exists")
            db.rollback()
        finally:
            db.close()
    if settings.profile_extractor != "rule_based" and settings.environment != "test":
        # Loading the multilingual encoder takes a few seconds; do it now, off
        # the request path, so the first person to speak is not kept waiting.
        threading.Thread(target=warm_up, args=(SessionLocal,), daemon=True).start()
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(self)"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Readable validation errors - these surface directly in the UI."""
    problems = [
        {
            "field": ".".join(str(p) for p in error["loc"][1:]) or error["loc"][0],
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Some of the information provided was not valid.", "problems": problems},
    )


@app.exception_handler(SQLAlchemyError)
async def database_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": (
                "The service could not reach its data store. Please try again in a moment."
            )
        },
    )


app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "api": settings.api_prefix,
        "demo_mode": settings.demo_mode,
    }
