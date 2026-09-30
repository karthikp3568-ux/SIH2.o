"""Skill-gap engine.

Compares a beneficiary's effective competence against the competencies a
qualification requires, and reports per-competency coverage with the reason.

Coverage bands are product decisions, documented in docs/ASSUMPTIONS.md:
  >= 0.60  covered    - the person can likely already do this
  >= 0.30  partial    - real transferable ground, but not sufficient alone
  <  0.30  missing    - has to be learned

Coverage for one competency is `max(skill_score x link_coverage)` over the
skills that evidence it - the strongest single piece of evidence, not a sum.
Summing would let three weakly related skills add up to a competency nobody
has actually demonstrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import BeneficiaryProfile, Qualification
from .skill_graph import SkillGraph, build_skill_graph

COVERED_THRESHOLD = 0.60
PARTIAL_THRESHOLD = 0.30


@dataclass
class CompetencyCoverage:
    code: str
    name: str
    nos_code: str | None
    is_core: bool
    weight: float
    coverage: float
    band: str  # covered | partial | missing
    #: Which of the beneficiary's skills contributed, and how.
    contributing_skills: list[dict] = field(default_factory=list)
    explanation: str = ""


@dataclass
class SkillGapReport:
    qualification_id: str
    qualification_code: str | None
    qualification_title: str
    nsqf_level: int | None
    #: Weighted share of core competencies already covered, 0..1.
    coverage_ratio: float = 0.0
    gap_ratio: float = 0.0
    gap_band: str = "moderate"  # small | moderate | large
    covered: list[CompetencyCoverage] = field(default_factory=list)
    partial: list[CompetencyCoverage] = field(default_factory=list)
    missing: list[CompetencyCoverage] = field(default_factory=list)
    #: Competencies ordered by how much they cost the person, most first.
    priority_order: list[str] = field(default_factory=list)

    @property
    def all_competencies(self) -> list[CompetencyCoverage]:
        return self.covered + self.partial + self.missing

    def to_dict(self) -> dict:
        def serialise(items: list[CompetencyCoverage]) -> list[dict]:
            return [
                {
                    "code": c.code,
                    "name": c.name,
                    "nos_code": c.nos_code,
                    "is_core": c.is_core,
                    "weight": c.weight,
                    "coverage": round(c.coverage, 3),
                    "band": c.band,
                    "contributing_skills": c.contributing_skills,
                    "explanation": c.explanation,
                }
                for c in items
            ]

        return {
            "qualification_id": self.qualification_id,
            "qualification_code": self.qualification_code,
            "qualification_title": self.qualification_title,
            "nsqf_level": self.nsqf_level,
            "coverage_ratio": round(self.coverage_ratio, 3),
            "gap_ratio": round(self.gap_ratio, 3),
            "gap_band": self.gap_band,
            "covered": serialise(self.covered),
            "partial": serialise(self.partial),
            "missing": serialise(self.missing),
            "priority_order": self.priority_order,
        }


def _band_for(gap_ratio: float) -> str:
    """Split the gap into thirds: mostly there, meaningful, or a long way off."""
    if gap_ratio <= 1 / 3:
        return "small"
    if gap_ratio <= 2 / 3:
        return "moderate"
    return "large"


def analyze_gap(
    db: Session,
    beneficiary: BeneficiaryProfile,
    qualification: Qualification,
    graph: SkillGraph | None = None,
) -> SkillGapReport:
    """Compute per-competency coverage for one target qualification."""
    graph = graph or build_skill_graph(db, beneficiary)
    node_map = graph.node_map()

    report = SkillGapReport(
        qualification_id=qualification.id,
        qualification_code=qualification.code,
        qualification_title=qualification.title,
        nsqf_level=qualification.nsqf_level,
    )

    total_weight = 0.0
    covered_weight = 0.0

    for link in sorted(qualification.competency_links, key=lambda l: l.sequence):
        competency = link.competency
        if competency is None:
            continue

        best_coverage = 0.0
        contributions: list[dict] = []
        for skill_link in competency.skill_links:
            skill = skill_link.skill
            if skill is None:
                continue
            node = node_map.get(skill.code)
            if node is None or node.score <= 0:
                continue
            contribution = node.score * skill_link.coverage
            best_coverage = max(best_coverage, contribution)
            contributions.append(
                {
                    "skill_code": skill.code,
                    "skill_name": skill.name,
                    "your_level": round(node.score, 3),
                    "counts_towards": skill_link.coverage,
                    "contribution": round(contribution, 3),
                    "is_direct": node.is_direct,
                    "derivation": node.derivation,
                    "verification_status": node.verification_status,
                }
            )

        contributions.sort(key=lambda c: -c["contribution"])
        band = (
            "covered"
            if best_coverage >= COVERED_THRESHOLD
            else "partial"
            if best_coverage >= PARTIAL_THRESHOLD
            else "missing"
        )
        coverage = CompetencyCoverage(
            code=competency.code,
            name=competency.name,
            nos_code=competency.nos_code,
            is_core=link.is_core,
            weight=link.weight,
            coverage=best_coverage,
            band=band,
            contributing_skills=contributions[:3],
            explanation=_explain(band, contributions),
        )

        if link.is_core:
            total_weight += link.weight
            covered_weight += link.weight * min(1.0, best_coverage)

        if band == "covered":
            report.covered.append(coverage)
        elif band == "partial":
            report.partial.append(coverage)
        else:
            report.missing.append(coverage)

    report.coverage_ratio = round(covered_weight / total_weight, 4) if total_weight else 0.0
    report.gap_ratio = round(1.0 - report.coverage_ratio, 4)
    report.gap_band = _band_for(report.gap_ratio)
    # What to learn first: heaviest core competencies with the least coverage.
    report.priority_order = [
        c.code
        for c in sorted(
            report.missing + report.partial,
            key=lambda c: (-(c.weight * (1 - c.coverage)), c.code),
        )
    ]
    return report


def _explain(band: str, contributions: list[dict]) -> str:
    if not contributions:
        return "You have not told us about any skill that covers this yet."
    top = contributions[0]
    basis = (
        f"your {top['skill_name'].lower()}"
        if top["is_direct"]
        else f"{top['derivation']}" if top["derivation"] else f"related work in {top['skill_name'].lower()}"
    )
    if band == "covered":
        return f"Largely covered by {basis}."
    if band == "partial":
        return f"Partly covered by {basis}, but not enough on its own."
    return f"Not covered. The closest thing you have is {basis}."


def analyze_gaps_for_qualifications(
    db: Session, beneficiary: BeneficiaryProfile, qualifications: list[Qualification]
) -> dict[str, SkillGapReport]:
    """Batch version - builds the skill graph once."""
    graph = build_skill_graph(db, beneficiary)
    return {q.id: analyze_gap(db, beneficiary, q, graph) for q in qualifications}


def aggregate_missing_competencies(reports: list[SkillGapReport]) -> list[dict]:
    """Most frequently missing competencies across reports, for analytics."""
    tally: dict[str, dict] = {}
    for report in reports:
        for competency in report.missing:
            entry = tally.setdefault(
                competency.code, {"code": competency.code, "name": competency.name, "count": 0}
            )
            entry["count"] += 1
    return sorted(tally.values(), key=lambda e: -e["count"])
