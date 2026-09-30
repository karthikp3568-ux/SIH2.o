"""API router aggregation."""

from fastapi import APIRouter

from . import admin, auth, beneficiary, catalog, conversation, demo, outcomes, recommendations, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(conversation.router)
api_router.include_router(conversation.speech_router)
api_router.include_router(conversation.channels_router)
api_router.include_router(beneficiary.router)
api_router.include_router(catalog.router)
api_router.include_router(recommendations.router)
api_router.include_router(outcomes.router)
api_router.include_router(admin.router)
api_router.include_router(demo.router)

__all__ = ["api_router"]
