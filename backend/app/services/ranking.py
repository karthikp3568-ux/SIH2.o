"""Hybrid ranking engine.

Every candidate that survived retrieval is scored on nine independent factors.
Each factor is a pure function of data we can point at, returns 0..1, and keeps
the sentence that explains it. The final score is the weighted mean, with
weights loaded from config/ranking_weights.json.

Two honesty notes, repeated in the UI and in docs/ASSUMPTIONS.md:
  * The weights are product judgement, not empirical findings. They were chosen
    so the ranking is legible and so no single factor can dominate. They should
    be re-tuned against the outcome data collected in Phase 4.
  * Semantic similarity does not appear in the score at all. It decides which
    candidates are retrieved; the ordering is then decided by these nine
    explicit factors.
"""

from __future__ import annotations

from dataclasses import dataclass, field


from ..config import get_ranking_config
from ..core.enums import (
    EDUCATION_RANK,
    GOAL_TO_OPPORTUNITY_AFFINITY,
    VERIFICATION_STRENGTH,
    GoalType,
    Mobility,
)
from ..core.geo import location_fit_score
from ..models import BeneficiaryProfile, Opportunity, as_aware
from .retrieval import Candidate, RetrievalContext
from .skill_gap import SkillGapReport
from .skill_graph import SkillGraph

MOBILITY_ORDER = {Mobility.LOW: 0, Mobility.MEDIUM: 1, Mobility.HIGH: 2}

#: The gap size we consider ideal: enough to be worth training for, small
#: enough to be achievable. Product judgement, see docs/ASSUMPTIONS.md.
IDEAL_GAP_RATIO = 0.35

#: Retrieval similarity deliberately does NOT feed the ranking score. It selects
#: the candidate pool; ranking then scores each candidate on factors that depend
#: only on that candidate and the beneficiary. Mixing a pool-normalised
#: similarity into the score would make one person's "skill fit" change
#: depending on what else happened to be retrieved - which is both unstable and
#: impossible to explain honestly to a beneficiary.


@dataclass
class Factor:
    code: str
    score: float
    weight: float
    label: str
    detail: str = ""

    @property
    def contribution(self) -> float:
        return round(self.score * self.weight, 4)


@dataclass
class ScoredCandidate:
    candidate: Candidate
    gap_report: SkillGapReport | None
    match_score: float
    factors: dict[str, Factor] = field(default_factory=dict)
    matched_skill_codes: list[str] = field(default_factory=list)
    missing_competency_codes: list[str] = field(default_factory=list)
    eligibility: str = "eligible"
    skill_fit_band: str = "moderate"
    mobility_fit_band: str = "moderate"
    availability: str = "active"
    skill_gap_band: str = "moderate"

    @property
    def opportunity(self) -> Opportunity:
        return self.candidate.opportunity

    def factor_scores(self) -> dict[str, float]:
        return {code: round(f.score, 4) for code, f in self.factors.items()}

    def factor_contributions(self) -> dict[str, float]:
        return {code: f.contribution for code, f in self.factors.items()}


def _band(score: float, thresholds: tuple[float, float, float] = (0.75, 0.55, 0.35)) -> str:
    high, good, moderate = thresholds
    if score >= high:
        return "high"
    if score >= good:
        return "good"
    if score >= moderate:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Individual factors
# ---------------------------------------------------------------------------


def _skill_fit(
    candidate: Candidate, graph: SkillGraph, gap_report: SkillGapReport | None
) -> tuple[float, list[str], str]:
    """How much of what this opportunity needs the person can already do."""
    scores = graph.score_map()
    required = list(candidate.opportunity.skill_codes or [])

    matched: list[str] = []
    if required:
        per_skill = []
        for code in required:
            held = min(1.0, scores.get(code, 0.0))
            per_skill.append(held)
            if held >= 0.45:
                matched.append(code)
        overlap = sum(per_skill) / len(per_skill)
        detail = f"{len(matched)} of {len(required)} listed skills already held"
    elif gap_report is not None:
        overlap = gap_report.coverage_ratio
        matched = [
            c.contributing_skills[0]["skill_code"]
            for c in gap_report.covered
            if c.contributing_skills
        ]
        detail = f"{int(gap_report.coverage_ratio * 100)}% of the qualification's competencies covered"
    else:
        overlap = 0.0
        detail = "no skill requirements listed for this opportunity"

    return round(min(1.0, overlap), 4), matched, detail


def _qualification_fit(
    candidate: Candidate, ctx: RetrievalContext, gap_report: SkillGapReport | None
) -> tuple[float, str, str]:
    """Eligibility plus whether the NSQF step is a sensible next move."""
    opportunity = candidate.opportunity
    held_rank = EDUCATION_RANK.get(ctx.education_level or "", 0)
    required_rank = EDUCATION_RANK.get(opportunity.education_required or "", 0)

    if opportunity.education_required and held_rank < required_rank:
        return 0.0, "not_eligible", (
            f"requires {opportunity.education_required.replace('_', ' ')}"
        )

    eligibility = "eligible"
    qualification = opportunity.qualification
    if qualification is None:
        # A listing not mapped to a recognised standard is harder to verify and
        # leads nowhere certifiable, so it should not score as well as one that is.
        return 0.6, eligibility, "no recognised qualification standard is linked to this listing"

    score = 0.85
    detail = "meets the stated education requirement"

    if qualification.nsqf_level:
        # Current level proxy: the highest NSQF level among competencies the
        # person already covers, else inferred from schooling.
        current_level = 2 + max(0, held_rank - 2)
        if gap_report is not None and gap_report.covered:
            covered_levels = [c for c in gap_report.covered if c.code]
            if covered_levels:
                current_level = max(
                    current_level,
                    max(
                        (qualification.nsqf_level - 1 if gap_report.coverage_ratio > 0.4 else 0),
                        current_level,
                    ),
                )
        step = qualification.nsqf_level - current_level
        if step == 1:
            score, detail = 1.0, f"NSQF level {qualification.nsqf_level} is one step up from where you are"
        elif step == 0:
            score, detail = 0.8, f"NSQF level {qualification.nsqf_level} matches your current level"
        elif step == 2:
            score, detail = 0.55, f"NSQF level {qualification.nsqf_level} is two steps up - a longer route"
            eligibility = "eligible_with_preparation"
        elif step >= 3:
            score, detail = 0.3, f"NSQF level {qualification.nsqf_level} is a large jump from your current level"
            eligibility = "eligible_with_preparation"
        else:
            score, detail = 0.5, f"NSQF level {qualification.nsqf_level} is below your current level"

    return round(score, 4), eligibility, detail


def _aspiration_fit(
    candidate: Candidate, beneficiary: BeneficiaryProfile
) -> tuple[float, str]:
    """Does this match what the person said they want, and what interests them?"""
    opportunity = candidate.opportunity
    goals = [g.goal_type for g in beneficiary.goals if g.is_active] or [GoalType.UNDECIDED]
    goal_score = max(
        GOAL_TO_OPPORTUNITY_AFFINITY.get(goal, {}).get(opportunity.opportunity_type, 0.5)
        for goal in goals
    )

    interest_tags = {i.tag or i.label.lower() for i in beneficiary.interests}
    interest_score = 0.5
    matched_interest = None
    if interest_tags:
        haystack = " ".join(
            filter(
                None,
                [
                    opportunity.title.lower(),
                    (opportunity.sector or "").lower(),
                    " ".join(opportunity.skill_codes or []),
                    " ".join(opportunity.skills_required or []).lower(),
                ],
            )
        )
        for tag in interest_tags:
            if tag and tag in haystack:
                interest_score = 1.0
                matched_interest = tag
                break
        else:
            interest_score = 0.35

    score = 0.6 * goal_score + 0.4 * interest_score
    goal_label = ", ".join(g.replace("_", " ") for g in goals)
    detail = f"you said you want {goal_label}"
    if matched_interest:
        detail += f"; matches your interest in {matched_interest.replace('_', ' ')}"
    return round(score, 4), detail


def _gap_compatibility(gap_report: SkillGapReport | None) -> tuple[float, str]:
    """Reward a gap that is worth closing and realistic to close.

    A zero gap means no progression; a very large gap means the person is not
    ready. The peak sits at IDEAL_GAP_RATIO.
    """
    if gap_report is None:
        return 0.5, "no linked qualification, so the skill gap could not be measured"
    distance = abs(gap_report.gap_ratio - IDEAL_GAP_RATIO)
    score = max(0.0, 1.0 - distance / 0.65)
    missing = len(gap_report.missing)
    detail = (
        f"{int(gap_report.coverage_ratio * 100)}% already covered, "
        f"{missing} competenc{'y' if missing == 1 else 'ies'} to learn"
    )
    return round(score, 4), detail


def _location_fit(candidate: Candidate, ctx: RetrievalContext) -> tuple[float, str]:
    distance = candidate.distance_km
    score = location_fit_score(distance, ctx.radius_km)
    if distance is None:
        return score, "exact distance unknown - location not confirmed"
    return score, f"{distance:.0f} km from your location"


def _mobility_fit(candidate: Candidate, beneficiary: BeneficiaryProfile) -> tuple[float, str, str]:
    required = MOBILITY_ORDER.get(candidate.opportunity.mobility_required, 0)
    available = MOBILITY_ORDER.get(beneficiary.mobility, 1)
    difference = required - available
    if difference <= 0:
        return 1.0, "high", "the travel this needs is within what you said you can manage"
    if difference == 1:
        return 0.4, "moderate", "this needs more travel than you said you prefer"
    return 0.1, "low", "this needs much more travel than you said you can manage"


def _availability(candidate: Candidate) -> tuple[float, str, str]:
    opportunity = candidate.opportunity
    if opportunity.seats_available is None:
        return 0.75, "active", "listed as open; seat count not published"
    if opportunity.seats_available <= 0:
        return 0.0, "full", "no seats currently available"
    if opportunity.seats_total:
        ratio = opportunity.seats_available / opportunity.seats_total
        label = "active" if ratio > 0.2 else "filling_fast"
        detail = f"{opportunity.seats_available} of {opportunity.seats_total} places open"
        return round(0.6 + 0.4 * min(1.0, ratio), 4), label, detail
    return 0.8, "active", f"{opportunity.seats_available} places open"


def _freshness(candidate: Candidate, ctx: RetrievalContext, config: dict) -> tuple[float, str]:
    last_verified = as_aware(candidate.opportunity.last_verified_at)
    if last_verified is None:
        return 0.0, "never verified"
    stale_after = int(config["freshness"]["stale_after_days"])
    age_days = (ctx.now - last_verified).days
    if age_days <= 7:
        score = 1.0
    elif age_days >= stale_after:
        score = 0.25
    else:
        score = round(1.0 - 0.75 * (age_days - 7) / (stale_after - 7), 4)
    return score, f"last verified {age_days} day(s) ago"


def _verification(candidate: Candidate) -> tuple[float, str]:
    opportunity = candidate.opportunity
    strength = VERIFICATION_STRENGTH.get(opportunity.verification_status, 0.35)
    score = round(0.5 * strength + 0.5 * opportunity.source_trust, 4)
    return score, (
        f"source: {opportunity.source}; status: "
        f"{opportunity.verification_status.replace('_', ' ')}"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def score_candidate(
    candidate: Candidate,
    beneficiary: BeneficiaryProfile,
    graph: SkillGraph,
    gap_report: SkillGapReport | None,
    ctx: RetrievalContext,
    config: dict | None = None,
) -> ScoredCandidate:
    config = config or get_ranking_config()
    weights: dict[str, float] = config["weights"]

    skill_score, matched, skill_detail = _skill_fit(candidate, graph, gap_report)
    qualification_score, eligibility, qualification_detail = _qualification_fit(
        candidate, ctx, gap_report
    )
    aspiration_score, aspiration_detail = _aspiration_fit(candidate, beneficiary)
    gap_score, gap_detail = _gap_compatibility(gap_report)
    location_score, location_detail = _location_fit(candidate, ctx)
    mobility_score, mobility_band, mobility_detail = _mobility_fit(candidate, beneficiary)
    availability_score, availability_label, availability_detail = _availability(candidate)
    freshness_score, freshness_detail = _freshness(candidate, ctx, config)
    verification_score, verification_detail = _verification(candidate)

    factors = {
        "skill_fit": Factor("skill_fit", skill_score, weights["skill_fit"], "Skill overlap", skill_detail),
        "qualification_fit": Factor(
            "qualification_fit", qualification_score, weights["qualification_fit"],
            "Eligibility and level", qualification_detail,
        ),
        "aspiration_fit": Factor(
            "aspiration_fit", aspiration_score, weights["aspiration_fit"],
            "What you said you want", aspiration_detail,
        ),
        "gap_compatibility": Factor(
            "gap_compatibility", gap_score, weights["gap_compatibility"],
            "How reachable the gap is", gap_detail,
        ),
        "location_fit": Factor(
            "location_fit", location_score, weights["location_fit"], "Distance", location_detail
        ),
        "mobility_fit": Factor(
            "mobility_fit", mobility_score, weights["mobility_fit"], "Travel needed", mobility_detail
        ),
        "availability": Factor(
            "availability", availability_score, weights["availability"], "Availability", availability_detail
        ),
        "freshness": Factor(
            "freshness", freshness_score, weights["freshness"], "How recently confirmed", freshness_detail
        ),
        "verification": Factor(
            "verification", verification_score, weights["verification"], "Source and verification",
            verification_detail,
        ),
    }

    total_weight = sum(f.weight for f in factors.values()) or 1.0
    match_score = round(sum(f.contribution for f in factors.values()) / total_weight, 4)

    return ScoredCandidate(
        candidate=candidate,
        gap_report=gap_report,
        match_score=match_score,
        factors=factors,
        matched_skill_codes=matched,
        missing_competency_codes=[c.code for c in gap_report.missing] if gap_report else [],
        eligibility=eligibility,
        skill_fit_band=_band(skill_score),
        mobility_fit_band=mobility_band,
        availability=availability_label,
        skill_gap_band=gap_report.gap_band if gap_report else "unknown",
    )


#: A candidate must connect to something the beneficiary actually told us -
#: either skill overlap or a stated interest. Below this, proximity and
#: availability alone could float an unrelated trade to the top, which is not a
#: recommendation so much as a coincidence.
RELEVANCE_FLOOR = 0.15


def is_credible(scored: ScoredCandidate) -> tuple[bool, str | None]:
    """Reject candidates with no substantive link to the person's profile.

    Returns (credible, reason). This is a relevance gate, not a quality gate:
    a genuinely related pathway with a large skill gap still passes.
    """
    skill_score = scored.factors["skill_fit"].score
    coverage = scored.gap_report.coverage_ratio if scored.gap_report else 0.0
    interest_matched = "matches your interest" in (scored.factors["aspiration_fit"].detail or "")

    if skill_score >= RELEVANCE_FLOOR or coverage >= RELEVANCE_FLOOR or interest_matched:
        return True, None
    return False, (
        "None of your skills or stated interests relate to this listing, so it was "
        "not offered as a pathway even though it is nearby and available."
    )


def rank_candidates(
    scored: list[ScoredCandidate], top_n: int | None = None, min_score: float | None = None
) -> list[ScoredCandidate]:
    """Sort, apply the minimum-score floor, and diversify the head of the list.

    Diversification matters: returning three near-identical training listings
    from one provider is technically well-ranked and practically useless.
    """
    config = get_ranking_config()
    top_n = top_n or int(config["top_n"])
    min_score = config["min_score"] if min_score is None else min_score

    eligible = [s for s in scored if s.match_score >= min_score]
    eligible.sort(key=lambda s: (-s.match_score, s.candidate.distance_km or 1e9))

    selected: list[ScoredCandidate] = []
    seen_types: dict[str, int] = {}
    seen_providers: set[str] = set()
    deferred: list[ScoredCandidate] = []

    for item in eligible:
        opportunity_type = item.opportunity.opportunity_type
        provider = item.opportunity.provider
        # At most two of one type, and one per provider, while alternatives exist.
        if seen_types.get(opportunity_type, 0) >= 2 or provider in seen_providers:
            deferred.append(item)
            continue
        selected.append(item)
        seen_types[opportunity_type] = seen_types.get(opportunity_type, 0) + 1
        seen_providers.add(provider)
        if len(selected) >= top_n:
            break

    # Backfill from the deferred list if diversification left us short.
    for item in deferred:
        if len(selected) >= top_n:
            break
        selected.append(item)

    return selected[:top_n]


def explain_weights(config: dict | None = None) -> list[dict]:
    """The weight table, for the admin UI and the API's transparency endpoint."""
    config = config or get_ranking_config()
    weights = config["weights"]
    total = sum(weights.values()) or 1.0
    labels = {
        "skill_fit": "Skills you already have",
        "qualification_fit": "Eligibility and level step",
        "aspiration_fit": "What you said you want",
        "gap_compatibility": "How reachable the skill gap is",
        "location_fit": "Distance from you",
        "mobility_fit": "Travel the opportunity needs",
        "availability": "Places currently available",
        "freshness": "How recently the listing was confirmed",
        "verification": "Source trust and verification status",
    }
    return [
        {
            "code": code,
            "label": labels.get(code, code),
            "weight": weight,
            "share": round(weight / total, 4),
        }
        for code, weight in sorted(weights.items(), key=lambda kv: -kv[1])
    ]
