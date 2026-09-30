"""Shared request/response schemas."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str
    detail: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class LocationIn(BaseModel):
    """A location plus how it was obtained - provenance is never optional."""

    label: str | None = Field(default=None, max_length=160)
    village: str | None = Field(default=None, max_length=120)
    block: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, pattern=r"^[1-9]\d{5}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    source: str = Field(default="manual", pattern="^(gps|manual|pincode_lookup|district_centroid|admin_entry|demo_seed|conversation)$")
    accuracy_m: float | None = Field(default=None, ge=0)


class LocationOut(BaseModel):
    id: str | None = None
    label: str | None = None
    village: str | None = None
    block: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str | None = None
    accuracy_m: float | None = None
    captured_at: str | None = None


class ProviderStatusOut(BaseModel):
    name: str
    kind: str
    configured: bool
    detail: str
    is_offline_default: bool = False


class SystemStatus(BaseModel):
    app_name: str
    version: str
    environment: str
    demo_mode: bool
    database: str
    providers: dict[str, list[ProviderStatusOut]]
    capabilities: dict[str, Any]
