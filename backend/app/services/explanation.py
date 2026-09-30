"""Explainability layer.

Explanations are *derived from the computed factors*, never authored freely.
Each line carries a stable reason code plus the contribution that produced it,
so the explanation and the score cannot drift apart. When an LLM is configured
it may only rephrase these lines into simpler language - it is given the lines
and told not to add anything, and its output is discarded if it changes the
number of lines or introduces digits that were not there.

Internal prompts and model reasoning are never exposed; only reason codes and
their human-readable rendering leave the service.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.enums import OpportunityType
from ..providers.llm import get_llm_provider
from ..providers.base import ProviderNotConfigured
from .ranking import ScoredCandidate

#: Factors strong enough to be worth showing as a positive reason.
POSITIVE_THRESHOLD = 0.6
#: Factors weak enough to be worth flagging as a caution.
CAUTION_THRESHOLD = 0.4


@dataclass
class ReasonLine:
    category: str  # why_fits | what_missing | next_step | caution
    code: str
    label: str
    detail: str | None = None
    contribution: float | None = None


FACTOR_REASON_CODES = {
    "skill_fit": "SKILL_OVERLAP",
    "qualification_fit": "ELIGIBLE_AND_RIGHT_LEVEL",
    "aspiration_fit": "MATCHES_YOUR_GOAL",
    "gap_compatibility": "REACHABLE_SKILL_GAP",
    "location_fit": "NEARBY",
    "mobility_fit": "FITS_YOUR_TRAVEL_LIMIT",
    "availability": "PLACES_AVAILABLE",
    "freshness": "RECENTLY_CONFIRMED",
    "verification": "VERIFIED_SOURCE",
}

CAUTION_CODES = {
    "location_fit": ("FURTHER_AWAY", "This is further away than your other options"),
    "mobility_fit": ("NEEDS_MORE_TRAVEL", "This needs more travel than you said you prefer"),
    "availability": ("FEW_PLACES", "Very few places appear to be left"),
    "freshness": ("NOT_RECENTLY_CONFIRMED", "This listing has not been confirmed recently"),
    "verification": ("SOURCE_NOT_INDEPENDENTLY_VERIFIED", "The provider's details are self declared and not independently verified"),
    "gap_compatibility": ("LARGER_GAP", "There is more to learn here than in your other options"),
    "skill_fit": ("LESS_SKILL_OVERLAP", "Less of your current skill carries over to this one"),
}


def _next_step_text(scored: ScoredCandidate) -> str:
    opportunity = scored.opportunity
    match opportunity.opportunity_type:
        case OpportunityType.TRAINING:
            centre = (
                opportunity.training_program.training_centre
                if opportunity.training_program
                else opportunity.provider
            )
            return (
                f"Contact {centre} to confirm the next batch date and the fee, "
                "then enrol. Take your education certificate with you."
            )
        case OpportunityType.APPRENTICESHIP:
            return (
                f"Apply to {opportunity.provider} for the apprenticeship. Ask about the "
                "stipend, the daily timing and which certificate it leads to."
            )
        case OpportunityType.JOB:
            return (
                f"Apply to {opportunity.provider}. Be ready to describe the repair work "
                "you already do - practical experience counts at the interview."
            )
        case OpportunityType.ENTERPRISE | OpportunityType.SELF_EMPLOYMENT:
            return (
                f"Speak to {opportunity.provider} about the enterprise pathway. Ask what "
                "support, tools and working capital are needed to start."
            )
        case _:
            return f"Contact {opportunity.provider} to find out how to take this forward."


def build_reasons(scored: ScoredCandidate) -> list[ReasonLine]:
    """Turn the scored factors and gap report into ordered explanation lines."""
    lines: list[ReasonLine] = []

    # --- why it fits ---
    strong = [
        factor
        for factor in scored.factors.values()
        if factor.score >= POSITIVE_THRESHOLD and factor.weight > 0
    ]
    strong.sort(key=lambda f: -f.contribution)
    for factor in strong[:5]:
        lines.append(
            ReasonLine(
                category="why_fits",
                code=FACTOR_REASON_CODES.get(factor.code, factor.code.upper()),
                label=factor.label,
                detail=factor.detail,
                contribution=factor.contribution,
            )
        )

    # Name the specific skills that carried over - the most convincing evidence.
    if scored.gap_report and scored.gap_report.covered:
        covered_names = [c.name for c in scored.gap_report.covered[:3]]
        lines.append(
            ReasonLine(
                category="why_fits",
                code="COMPETENCIES_ALREADY_COVERED",
                label="You already cover: " + "; ".join(covered_names),
                detail=scored.gap_report.covered[0].explanation,
            )
        )

    # --- what is missing ---
    if scored.gap_report:
        core_missing = [c for c in scored.gap_report.missing if c.is_core]
        for competency in core_missing[:5]:
            lines.append(
                ReasonLine(
                    category="what_missing",
                    code="MISSING_COMPETENCY",
                    label=competency.name,
                    detail=(competency.nos_code or "") + (f" - {competency.explanation}" if competency.explanation else ""),
                )
            )
        for competency in scored.gap_report.partial[:3]:
            lines.append(
                ReasonLine(
                    category="what_missing",
                    code="PARTIAL_COMPETENCY",
                    label=f"{competency.name} (partly covered)",
                    detail=competency.explanation,
                )
            )
    if scored.eligibility == "eligible_with_preparation":
        lines.append(
            ReasonLine(
                category="what_missing",
                code="PREPARATION_NEEDED",
                label="This is more than one level above your current work",
                detail=scored.factors["qualification_fit"].detail,
            )
        )

    # --- cautions ---
    for code, factor in scored.factors.items():
        if factor.score < CAUTION_THRESHOLD and code in CAUTION_CODES:
            reason_code, label = CAUTION_CODES[code]
            lines.append(
                ReasonLine(category="caution", code=reason_code, label=label, detail=factor.detail)
            )

    # --- next step ---
    lines.append(
        ReasonLine(category="next_step", code="NEXT_STEP", label=_next_step_text(scored))
    )
    return lines


def next_step_for(scored: ScoredCandidate) -> str:
    return _next_step_text(scored)


# ---------------------------------------------------------------------------
# Optional LLM rephrasing
# ---------------------------------------------------------------------------

_REPHRASE_SYSTEM = """You rewrite short explanation lines for a rural job seeker in India who may read slowly.

Strict rules:
- Rewrite ONLY the lines given. Do not add, merge, remove or reorder lines.
- Do not introduce any fact, number, place, employer or qualification that is not already in the line.
- Keep each line under 18 words. Use simple, direct words.
- Output exactly one rewritten line per input line, numbered the same way."""


def polish_reasons(lines: list[ReasonLine], language: str = "en") -> list[ReasonLine]:
    """Optionally simplify the wording. Silently keeps the originals on any doubt."""
    provider = get_llm_provider()
    if not provider.available or not lines:
        return lines

    numbered = "\n".join(f"{i + 1}. {line.label}" for i, line in enumerate(lines))
    try:
        raw = provider.complete(
            _REPHRASE_SYSTEM,
            f"Rewrite these lines in {language}:\n{numbered}",
            max_tokens=500,
        )
    except ProviderNotConfigured:
        return lines

    rewritten = [
        part.split(".", 1)[-1].strip()
        for part in raw.strip().splitlines()
        if part.strip() and part.strip()[0].isdigit()
    ]
    # Guard: a different line count, or a new number appearing, means the model
    # did something other than rephrase. Discard it.
    if len(rewritten) != len(lines):
        return lines
    for original, new in zip(lines, rewritten, strict=True):
        original_digits = {c for c in (original.label or "") if c.isdigit()}
        new_digits = {c for c in new if c.isdigit()}
        if new_digits - original_digits:
            return lines
    for original, new in zip(lines, rewritten, strict=True):
        original.label = new
    return lines
