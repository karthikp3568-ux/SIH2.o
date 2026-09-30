"""Opportunity and qualification ingestion providers.

The MVP runs entirely off the seed and CSV providers, so the demo never depends
on an external API being reachable. `HttpOpportunityProvider` is a real generic
JSON client for a future NCS/SIDH/provider feed; it stays inert until a URL is
supplied.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..config import BACKEND_ROOT
from .base import ProviderNotConfigured, ProviderStatus

SEED_DIR = BACKEND_ROOT / "app" / "seed" / "data"

#: Columns a CSV import must provide; everything else is optional.
CSV_REQUIRED_COLUMNS = {"title", "provider", "opportunity_type", "description", "source"}

#: Comma-separated CSV columns that become JSON lists.
CSV_LIST_COLUMNS = {"skills_required", "competencies_required", "languages_of_instruction"}

CSV_FLOAT_COLUMNS = {"latitude", "longitude", "source_trust"}
CSV_INT_COLUMNS = {
    "min_age",
    "max_age",
    "stipend_or_income_inr",
    "seats_total",
    "seats_available",
    "duration_hours",
    "duration_weeks",
    "fee_inr",
}
CSV_BOOL_COLUMNS = {"is_remote_or_local", "is_subsidised"}


def _load_json(filename: str) -> list[dict[str, Any]]:
    path = SEED_DIR / filename
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else data.get("records", [])


class SeedOpportunityProvider:
    """Curated, hand-verified demo records shipped with the repository."""

    name = "seed"

    def status(self) -> ProviderStatus:
        count = len(_load_json("opportunities.json"))
        return ProviderStatus(
            name=self.name,
            kind="opportunity",
            configured=True,
            detail=f"{count} curated demo opportunity records bundled with the app.",
            is_offline_default=True,
        )

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        return _load_json("opportunities.json")


class CsvOpportunityProvider:
    """Import opportunities from a CSV file.

    Rows that fail validation are reported, not silently dropped - see
    `scripts/import_opportunities.py`.
    """

    name = "csv_import"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="opportunity",
            configured=self.path.exists(),
            detail=(
                f"CSV source {self.path}"
                if self.path.exists()
                else f"CSV file not found: {self.path}"
            ),
        )

    @staticmethod
    def coerce_row(row: dict[str, str]) -> dict[str, Any]:
        """Convert CSV strings into the types the Opportunity model expects."""
        record: dict[str, Any] = {}
        for key, raw in row.items():
            if key is None:
                continue
            key = key.strip()
            value = (raw or "").strip()
            if value == "":
                continue
            if key in CSV_LIST_COLUMNS:
                record[key] = [part.strip() for part in value.split(",") if part.strip()]
            elif key in CSV_FLOAT_COLUMNS:
                record[key] = float(value)
            elif key in CSV_INT_COLUMNS:
                record[key] = int(float(value))
            elif key in CSV_BOOL_COLUMNS:
                record[key] = value.lower() in {"1", "true", "yes", "y"}
            else:
                record[key] = value
        return record

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        if not self.path.exists():
            raise ProviderNotConfigured(f"CSV file not found: {self.path}")
        with self.path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = CSV_REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"CSV is missing required columns: {', '.join(sorted(missing))}"
                )
            return [self.coerce_row(row) for row in reader]


class HttpOpportunityProvider:
    """Generic JSON feed client for a future upstream opportunity source.

    Inert unless a URL is supplied. It performs no transformation beyond
    extracting a list, so a concrete integration supplies a `mapper`.
    """

    name = "http_api"

    def __init__(self, url: str | None = None, mapper=None, headers: dict | None = None) -> None:
        self.url = url
        self.mapper = mapper
        self.headers = headers or {}

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="opportunity",
            configured=bool(self.url),
            detail=(
                f"Configured against {self.url}"
                if self.url
                else "No upstream opportunity API configured. Seed and CSV sources are in use."
            ),
        )

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        if not self.url:
            raise ProviderNotConfigured("No opportunity API URL configured.")
        import httpx  # noqa: PLC0415 - only needed on the configured path

        response = httpx.get(self.url, headers=self.headers, timeout=30.0, params=kwargs)
        response.raise_for_status()
        body = response.json()
        records = body if isinstance(body, list) else body.get("records", body.get("data", []))
        return [self.mapper(r) for r in records] if self.mapper else records


class SeedQualificationProvider:
    """Recognised qualification/competency records bundled with the app.

    IMPORTANT: these records are a *representative sample* modelled on the
    NSQF/QP/NOS structure for demonstration. They carry `source` and
    `last_verified_at` so their provenance is visible, and they must be replaced
    with an authoritative feed before any real-world use. See docs/ASSUMPTIONS.md.
    """

    name = "seed"

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="qualification",
            configured=True,
            detail=(
                f"{len(_load_json('qualifications.json'))} sample qualification records "
                "modelled on the NSQF/QP/NOS structure. Demonstration data, not an "
                "authoritative extract."
            ),
            is_offline_default=True,
        )

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        return _load_json("qualifications.json")


def load_seed_file(filename: str) -> list[dict[str, Any]]:
    """Public helper used by the seeder for taxonomy/competency/knowledge files."""
    return _load_json(filename)


def all_data_source_statuses() -> list[ProviderStatus]:
    return [
        SeedOpportunityProvider().status(),
        SeedQualificationProvider().status(),
        HttpOpportunityProvider().status(),
    ]
