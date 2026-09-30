"""Hybrid retrieval: semantic + keyword + structured metadata filters.

Three deliberate design choices:

1. **Structured filters are hard gates, applied in SQL and Python before any
   scoring.** Expired, inactive, unverified-for-a-year, ineligible and
   out-of-range records are removed outright and recorded as *exclusions with a
   reason*, so "why did I not see X" is answerable.

2. **Similarity alone never decides anything.** The vector score is blended
   with BM25 keyword scoring, and the blend only produces a candidate pool -
   final ordering comes from the hybrid ranker in ranking.py.

3. **Query expansion runs over the skill taxonomy**, not over a language model.
   "pump repair" expands to its aliases, parents and transfer targets, which is
   what lets a lexical retriever behave semantically without a neural model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_ranking_config
from ..core.enums import EDUCATION_RANK, Mobility, RecordStatus
from ..core.geo import bounding_box, distance_between
from ..models import (
    BeneficiaryProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    Opportunity,
    Qualification,
    Skill,
    SkillAlias,
    SkillRelation,
    as_aware,
    utcnow,
)

#: Below this many opportunity rows we evaluate every record so that each
#: exclusion carries an exact reason; above it we prefilter geographically.
BOUNDING_BOX_THRESHOLD = 500
from ..providers.embeddings import get_embedding_provider
from .language_id import normalize_text
from .skill_graph import SkillGraph, build_skill_graph

# Reason codes for hard exclusions. Stable identifiers - the UI maps them to
# translated text.
EXCLUSION_REASONS: dict[str, str] = {
    "INACTIVE_STATUS": "The listing is not currently active",
    "EXPIRED": "The listing's validity date has passed",
    "NOT_YET_OPEN": "The listing has not opened yet",
    "STALE_UNVERIFIED": "The listing has not been re-verified for over a year",
    "NO_SEATS": "No seats or vacancies are currently available",
    "RETIRED_QUALIFICATION": "It is based on a qualification standard that has been retired",
    "EDUCATION_NOT_MET": "The minimum education requirement is not met",
    "AGE_OUT_OF_RANGE": "The age requirement is not met",
    "BEYOND_TRAVEL_RANGE": "It is further than the stated travel limit",
    "NO_PROFILE_OVERLAP": "It does not relate to any skill or interest in the profile",
}


@dataclass
class RetrievalContext:
    query_text: str
    expanded_terms: list[str] = field(default_factory=list)
    education_level: str | None = None
    age: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float = 60.0
    mobility: str = Mobility.MEDIUM
    opportunity_types: list[str] | None = None
    sectors: list[str] | None = None
    now: datetime = field(default_factory=utcnow)
    pool_size: int = 60
    #: When True, education and distance gates are relaxed. Used only by the
    #: explicit "search wider" retry, never silently.
    relax_filters: bool = False


@dataclass
class Exclusion:
    opportunity_id: str
    title: str
    reason_code: str
    reason: str
    detail: str | None = None

    def as_dict(self) -> dict:
        return {
            "opportunity_id": self.opportunity_id,
            "title": self.title,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass
class Candidate:
    opportunity: Opportunity
    distance_km: float | None
    vector_score: float = 0.0
    keyword_score: float = 0.0
    retrieval_score: float = 0.0
    evidence_chunk_ids: list[str] = field(default_factory=list)
    evidence_text: str = ""


@dataclass
class RetrievalResult:
    candidates: list[Candidate] = field(default_factory=list)
    exclusions: list[Exclusion] = field(default_factory=list)
    considered: int = 0
    passed_filters: int = 0
    used_vector: bool = True


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def build_query(
    db: Session, beneficiary: BeneficiaryProfile, graph: SkillGraph | None = None
) -> tuple[str, list[str]]:
    """Compose the retrieval query and its taxonomy expansion.

    Returns (query_text, expanded_terms). The expansion is what carries the
    semantics: aliases give surface variants, parents give the broader field,
    and transfer edges give adjacent trades the person could move into.
    """
    graph = graph or build_skill_graph(db, beneficiary)
    direct = [n for n in graph.nodes if n.is_direct and not n.is_category]
    direct.sort(key=lambda n: -n.score)

    parts: list[str] = []
    terms: list[str] = []

    if direct:
        names = [n.name for n in direct[:6]]
        parts.append("Skills already held: " + ", ".join(names) + ".")
        terms.extend(names)

    occupations = [o.title for o in beneficiary.occupations if o.is_current]
    if occupations:
        parts.append("Currently works in: " + ", ".join(occupations) + ".")
        terms.extend(occupations)

    interests = [i.label for i in beneficiary.interests]
    if interests:
        parts.append("Interested in: " + ", ".join(interests) + ".")
        terms.extend(i.tag or i.label for i in beneficiary.interests)

    goals = [g.goal_type.replace("_", " ") for g in beneficiary.goals if g.is_active]
    if goals:
        parts.append("Looking for: " + ", ".join(goals) + ".")
        terms.extend(goals)

    educations = sorted(
        beneficiary.educations, key=lambda e: EDUCATION_RANK.get(e.level, 0), reverse=True
    )
    if educations:
        parts.append(f"Education: {educations[0].level.replace('_', ' ')}.")

    parts.append(f"Able to travel: {beneficiary.mobility} distance.")

    # Expand through the taxonomy.
    direct_ids = [n.skill_id for n in direct]
    if direct_ids:
        alias_rows = db.execute(
            select(SkillAlias.alias).where(SkillAlias.skill_id.in_(direct_ids))
        ).scalars().all()
        terms.extend(alias_rows)

        skills = db.execute(select(Skill).where(Skill.id.in_(direct_ids))).scalars().all()
        parent_ids = [s.parent_id for s in skills if s.parent_id]
        if parent_ids:
            terms.extend(
                db.execute(select(Skill.name).where(Skill.id.in_(parent_ids))).scalars().all()
            )

        transfer_ids = db.execute(
            select(SkillRelation.to_skill_id).where(
                SkillRelation.from_skill_id.in_(direct_ids),
                SkillRelation.weight >= 0.4,
            )
        ).scalars().all()
        if transfer_ids:
            terms.extend(
                db.execute(select(Skill.name).where(Skill.id.in_(transfer_ids))).scalars().all()
            )

    # De-duplicate case-insensitively, preserving order.
    seen: set[str] = set()
    expanded: list[str] = []
    for term in terms:
        key = normalize_text(str(term))
        if key and key not in seen:
            seen.add(key)
            expanded.append(str(term))

    query_text = " ".join(parts)
    if expanded:
        query_text += " Related terms: " + ", ".join(expanded[:40]) + "."
    return query_text, expanded


def context_for(
    db: Session,
    beneficiary: BeneficiaryProfile,
    *,
    radius_km: float | None = None,
    graph: SkillGraph | None = None,
    relax_filters: bool = False,
) -> RetrievalContext:
    config = get_ranking_config()
    query_text, expanded = build_query(db, beneficiary, graph)
    location = beneficiary.primary_location
    education = sorted(
        beneficiary.educations, key=lambda e: EDUCATION_RANK.get(e.level, 0), reverse=True
    )
    radii = config["mobility_radius_km"]
    effective_radius = (
        radius_km
        if radius_km is not None
        else beneficiary.max_travel_km or radii.get(beneficiary.mobility, radii["medium"])
    )
    return RetrievalContext(
        query_text=query_text,
        expanded_terms=expanded,
        education_level=education[0].level if education else None,
        age=beneficiary.age,
        latitude=location.latitude if location else None,
        longitude=location.longitude if location else None,
        radius_km=float(effective_radius),
        mobility=beneficiary.mobility,
        pool_size=int(config["retrieval"]["candidate_pool"]),
        relax_filters=relax_filters,
    )


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def _hard_filter(
    opportunity: Opportunity, ctx: RetrievalContext, config: dict
) -> tuple[bool, Exclusion | None, float | None]:
    """Apply every non-negotiable gate. Returns (keep, exclusion, distance_km)."""
    now = ctx.now
    hard_stale_days = int(config["freshness"]["hard_stale_days"])

    def reject(code: str, detail: str | None = None) -> tuple[bool, Exclusion, None]:
        return (
            False,
            Exclusion(
                opportunity_id=opportunity.id,
                title=opportunity.title,
                reason_code=code,
                reason=EXCLUSION_REASONS[code],
                detail=detail,
            ),
            None,
        )

    if opportunity.status != RecordStatus.ACTIVE:
        return reject("INACTIVE_STATUS", f"status is '{opportunity.status}'")

    valid_until = as_aware(opportunity.valid_until)
    if valid_until is not None and valid_until < now:
        return reject("EXPIRED", f"valid until {valid_until.date().isoformat()}")

    valid_from = as_aware(opportunity.valid_from)
    if valid_from is not None and valid_from > now:
        return reject("NOT_YET_OPEN", f"opens {valid_from.date().isoformat()}")

    last_verified = as_aware(opportunity.last_verified_at)
    if last_verified is None or last_verified < now - timedelta(days=hard_stale_days):
        return reject(
            "STALE_UNVERIFIED",
            "never verified"
            if last_verified is None
            else f"last verified {last_verified.date().isoformat()}",
        )

    if opportunity.seats_available is not None and opportunity.seats_available <= 0:
        return reject("NO_SEATS")

    qualification = opportunity.qualification
    if qualification is not None:
        if qualification.status == RecordStatus.RETIRED:
            detail = f"{qualification.code or qualification.title} is retired"
            if qualification.superseded_by_code:
                detail += f", superseded by {qualification.superseded_by_code}"
            return reject("RETIRED_QUALIFICATION", detail)
        qualification_valid_until = as_aware(qualification.valid_until)
        if qualification_valid_until is not None and qualification_valid_until < now:
            return reject(
                "RETIRED_QUALIFICATION",
                f"{qualification.code or qualification.title} expired on "
                f"{qualification_valid_until.date().isoformat()}",
            )

    if not ctx.relax_filters and opportunity.education_required and ctx.education_level:
        required = EDUCATION_RANK.get(opportunity.education_required, 0)
        held = EDUCATION_RANK.get(ctx.education_level, 0)
        if held < required:
            return reject(
                "EDUCATION_NOT_MET",
                f"requires {opportunity.education_required.replace('_', ' ')}, "
                f"you have {ctx.education_level.replace('_', ' ')}",
            )

    if ctx.age is not None:
        if opportunity.min_age is not None and ctx.age < opportunity.min_age:
            return reject("AGE_OUT_OF_RANGE", f"minimum age {opportunity.min_age}")
        if opportunity.max_age is not None and ctx.age > opportunity.max_age:
            return reject("AGE_OUT_OF_RANGE", f"maximum age {opportunity.max_age}")

    distance = distance_between(
        ctx.latitude, ctx.longitude, opportunity.latitude, opportunity.longitude
    )
    if distance is not None and not ctx.relax_filters and distance > ctx.radius_km:
        return reject(
            "BEYOND_TRAVEL_RANGE",
            f"{distance:.0f} km away, beyond your {ctx.radius_km:.0f} km travel limit",
        )

    return True, None, distance


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _bm25_scores(query_terms: list[str], documents: dict[str, str]) -> dict[str, float]:
    """Standard BM25 over a small in-memory corpus.

    The corpus here is the filtered candidate set (tens of records), so an
    in-process implementation is appropriate. On PostgreSQL this is the natural
    place to swap in `ts_rank_cd` over a tsvector column.
    """
    if not documents or not query_terms:
        return {}
    k1, b = 1.5, 0.75
    tokenised = {doc_id: normalize_text(text).split() for doc_id, text in documents.items()}
    lengths = {doc_id: len(tokens) for doc_id, tokens in tokenised.items()}
    avg_length = sum(lengths.values()) / len(lengths) if lengths else 0.0
    if avg_length == 0:
        return {doc_id: 0.0 for doc_id in documents}

    terms: list[str] = []
    for term in query_terms:
        terms.extend(normalize_text(term).split())
    terms = [t for t in terms if len(t) > 2]
    if not terms:
        return {doc_id: 0.0 for doc_id in documents}

    total_docs = len(tokenised)
    scores: dict[str, float] = {doc_id: 0.0 for doc_id in documents}
    for term in set(terms):
        containing = sum(1 for tokens in tokenised.values() if term in tokens)
        if containing == 0:
            continue
        idf = math.log(1 + (total_docs - containing + 0.5) / (containing + 0.5))
        for doc_id, tokens in tokenised.items():
            frequency = tokens.count(term)
            if frequency == 0:
                continue
            denominator = frequency + k1 * (1 - b + b * lengths[doc_id] / avg_length)
            scores[doc_id] += idf * (frequency * (k1 + 1)) / denominator
    return scores


def _normalise(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return {k: (1.0 if high > 0 else 0.0) for k in scores}
    return {k: (v - low) / (high - low) for k, v in scores.items()}


def retrieve(db: Session, ctx: RetrievalContext) -> RetrievalResult:
    """Run the full retrieval pipeline and return a scored candidate pool."""
    config = get_ranking_config()
    result = RetrievalResult()

    total_records = db.execute(select(func.count(Opportunity.id))).scalar_one()
    result.considered = int(total_records)

    query = select(Opportunity).options(
        selectinload(Opportunity.qualification).selectinload(Qualification.competency_links),
        selectinload(Opportunity.training_program),
    )
    if ctx.opportunity_types:
        query = query.where(Opportunity.opportunity_type.in_(ctx.opportunity_types))

    # Index-friendly geographic prefilter, used only once the table is large
    # enough to need it. Below the threshold every record is evaluated, so each
    # exclusion carries its true reason instead of a generic "out of range".
    # On PostgreSQL this whole block becomes a single ST_DWithin predicate.
    use_bounding_box = (
        total_records > BOUNDING_BOX_THRESHOLD
        and ctx.latitude is not None
        and ctx.longitude is not None
        and not ctx.relax_filters
    )
    if use_bounding_box:
        min_lat, max_lat, min_lon, max_lon = bounding_box(
            ctx.latitude, ctx.longitude, ctx.radius_km
        )
        # Records without coordinates are kept and scored with a neutral
        # location factor rather than silently dropped.
        query = query.where(
            or_(
                Opportunity.latitude.is_(None),
                Opportunity.longitude.is_(None),
                (Opportunity.latitude.between(min_lat, max_lat))
                & (Opportunity.longitude.between(min_lon, max_lon)),
            )
        )

    opportunities = db.execute(query).scalars().unique().all()

    kept: list[Candidate] = []
    for opportunity in opportunities:
        keep, exclusion, distance = _hard_filter(opportunity, ctx, config)
        if not keep and exclusion is not None:
            result.exclusions.append(exclusion)
            continue
        kept.append(Candidate(opportunity=opportunity, distance_km=distance))

    if use_bounding_box:
        # Summarise what the prefilter removed so the count still reconciles.
        excluded_by_box = total_records - len(opportunities)
        if excluded_by_box > 0:
            result.exclusions.append(
                Exclusion(
                    opportunity_id="",
                    title=f"{excluded_by_box} further listing(s)",
                    reason_code="BEYOND_TRAVEL_RANGE",
                    reason=EXCLUSION_REASONS["BEYOND_TRAVEL_RANGE"],
                    detail=f"outside the {ctx.radius_km:.0f} km search area",
                )
            )

    result.passed_filters = len(kept)
    if not kept:
        return result

    # --- semantic + keyword scoring over the knowledge store ---
    opportunity_ids = [c.opportunity.id for c in kept]
    chunk_rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument.entity_id)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeDocument.entity_type == "opportunity",
            KnowledgeDocument.entity_id.in_(opportunity_ids),
            KnowledgeChunk.status == RecordStatus.ACTIVE,
        )
    ).all()

    texts_by_opportunity: dict[str, str] = {}
    chunks_by_opportunity: dict[str, list[KnowledgeChunk]] = {}
    for chunk, entity_id in chunk_rows:
        chunks_by_opportunity.setdefault(entity_id, []).append(chunk)
        texts_by_opportunity[entity_id] = (
            texts_by_opportunity.get(entity_id, "") + " " + chunk.text
        ).strip()

    # If the knowledge base has not been built, fall back to the record's own
    # text rather than returning nothing.
    if not texts_by_opportunity:
        result.used_vector = False
        from ..rag.ingest import build_opportunity_text  # noqa: PLC0415 - avoid import cycle

        texts_by_opportunity = {
            c.opportunity.id: build_opportunity_text(c.opportunity) for c in kept
        }

    provider = get_embedding_provider()
    query_vector = np.asarray(provider.embed_one(ctx.query_text), dtype=np.float32)
    vector_scores: dict[str, float] = {}
    for candidate in kept:
        best = 0.0
        best_chunk_ids: list[str] = []
        for chunk in chunks_by_opportunity.get(candidate.opportunity.id, []):
            if not chunk.embedding or chunk.embedding_dim != provider.dim:
                continue
            vector = np.asarray(chunk.embedding, dtype=np.float32)
            denominator = float(np.linalg.norm(query_vector) * np.linalg.norm(vector))
            similarity = float(np.dot(query_vector, vector) / denominator) if denominator else 0.0
            if similarity > best:
                best = similarity
                best_chunk_ids = [chunk.id]
        vector_scores[candidate.opportunity.id] = max(0.0, best)
        candidate.evidence_chunk_ids = best_chunk_ids
        candidate.evidence_text = texts_by_opportunity.get(candidate.opportunity.id, "")[:600]

    if not any(vector_scores.values()):
        result.used_vector = False

    keyword_scores = _bm25_scores(
        ctx.expanded_terms or [ctx.query_text], texts_by_opportunity
    )

    normalised_vector = _normalise(vector_scores)
    normalised_keyword = _normalise(keyword_scores)
    vector_weight = float(config["retrieval"]["vector_weight"])
    keyword_weight = float(config["retrieval"]["keyword_weight"])

    for candidate in kept:
        oid = candidate.opportunity.id
        candidate.vector_score = round(normalised_vector.get(oid, 0.0), 4)
        candidate.keyword_score = round(normalised_keyword.get(oid, 0.0), 4)
        candidate.retrieval_score = round(
            vector_weight * candidate.vector_score + keyword_weight * candidate.keyword_score, 4
        )

    kept.sort(key=lambda c: -c.retrieval_score)
    result.candidates = kept[: ctx.pool_size]
    return result
