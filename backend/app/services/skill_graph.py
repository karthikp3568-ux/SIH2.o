"""Build a beneficiary's skill graph and compute effective competence.

A held skill is worth something beyond itself: it rolls up into its parent
category and transfers partially along typed edges ("pump repair transfers to
motor rewinding at 0.5"). `effective_skill_scores` makes that explicit and
traceable - every derived score records how it was derived, which is what lets
the explanation layer say *why* a person partly covers a competency they never
claimed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.enums import (
    CONFIDENCE_SCORE,
    PROFICIENCY_SCORE,
    VERIFICATION_STRENGTH,
)
from ..models import BeneficiaryProfile, BeneficiarySkill, Skill, SkillRelation

#: A parent category is considered partly held when a child is held.
PARENT_ROLLUP = 0.7
#: Transfer decays once; we do not chain transfers, which would inflate scores.
MAX_TRANSFER_HOPS = 1


@dataclass
class SkillNode:
    code: str
    name: str
    skill_id: str
    score: float
    is_direct: bool
    is_category: bool
    proficiency: str | None = None
    source: str | None = None
    confidence: str | None = None
    verification_status: str | None = None
    evidence_strength: float = 0.0
    years_experience: float | None = None
    derived_from: str | None = None
    derivation: str | None = None


@dataclass
class SkillEdge:
    source: str
    target: str
    relation: str
    weight: float


@dataclass
class SkillGraph:
    nodes: list[SkillNode] = field(default_factory=list)
    edges: list[SkillEdge] = field(default_factory=list)

    def score_map(self) -> dict[str, float]:
        return {node.code: node.score for node in self.nodes}

    def node_map(self) -> dict[str, SkillNode]:
        return {node.code: node for node in self.nodes}

    def direct_codes(self) -> set[str]:
        return {n.code for n in self.nodes if n.is_direct}

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {
                    "code": n.code,
                    "name": n.name,
                    "score": round(n.score, 3),
                    "is_direct": n.is_direct,
                    "is_category": n.is_category,
                    "proficiency": n.proficiency,
                    "source": n.source,
                    "confidence": n.confidence,
                    "verification_status": n.verification_status,
                    "evidence_strength": round(n.evidence_strength, 3),
                    "years_experience": n.years_experience,
                    "derived_from": n.derived_from,
                    "derivation": n.derivation,
                }
                for n in sorted(self.nodes, key=lambda n: (-n.score, n.name))
            ],
            "edges": [
                {"source": e.source, "target": e.target, "relation": e.relation, "weight": e.weight}
                for e in self.edges
            ],
        }


def _direct_score(link: BeneficiarySkill) -> float:
    """Proficiency tempered by how confident we are that the claim is right.

    Verification status is *not* multiplied in here. An unverified but real
    skill is still real competence; verification is scored separately so the
    UI can show "you have this, but it is not certified yet" rather than
    quietly discounting the person's actual ability.
    """
    proficiency = PROFICIENCY_SCORE.get(link.proficiency, 0.45)
    confidence = CONFIDENCE_SCORE.get(link.confidence, 0.7)
    return round(proficiency * (0.55 + 0.45 * confidence), 4)


def build_skill_graph(db: Session, beneficiary: BeneficiaryProfile) -> SkillGraph:
    """Construct the beneficiary's skill graph with roll-up and transfer."""
    links = (
        db.execute(
            select(BeneficiarySkill)
            .options(selectinload(BeneficiarySkill.skill))
            .where(
                BeneficiarySkill.beneficiary_id == beneficiary.id,
                BeneficiarySkill.is_active.is_(True),
                BeneficiarySkill.skill_id.is_not(None),
            )
        )
        .scalars()
        .all()
    )

    all_skills = {s.id: s for s in db.execute(select(Skill)).scalars().all()}
    by_code = {s.code: s for s in all_skills.values()}

    nodes: dict[str, SkillNode] = {}
    edges: list[SkillEdge] = []

    # 1. Direct holdings.
    for link in links:
        skill = link.skill or all_skills.get(link.skill_id)
        if skill is None:
            continue
        score = _direct_score(link)
        existing = nodes.get(skill.code)
        if existing and existing.score >= score:
            continue
        nodes[skill.code] = SkillNode(
            code=skill.code,
            name=skill.name,
            skill_id=skill.id,
            score=score,
            is_direct=True,
            is_category=skill.is_category,
            proficiency=link.proficiency,
            source=link.source,
            confidence=link.confidence,
            verification_status=link.verification_status,
            evidence_strength=VERIFICATION_STRENGTH.get(link.verification_status, 0.35),
            years_experience=link.years_experience,
        )

    direct_codes = set(nodes)

    # 2. Roll up into ancestor categories.
    for code in list(direct_codes):
        skill = by_code.get(code)
        child_score = nodes[code].score
        hops = 0
        while skill and skill.parent_id and hops < 4:
            parent = all_skills.get(skill.parent_id)
            if parent is None:
                break
            rolled = round(child_score * (PARENT_ROLLUP ** (hops + 1)), 4)
            current = nodes.get(parent.code)
            if current is None or (not current.is_direct and current.score < rolled):
                nodes[parent.code] = SkillNode(
                    code=parent.code,
                    name=parent.name,
                    skill_id=parent.id,
                    score=rolled,
                    is_direct=False,
                    is_category=parent.is_category,
                    derived_from=code,
                    derivation=f"rolled up from {nodes[code].name}",
                )
            edges.append(SkillEdge(source=code, target=parent.code, relation="part_of", weight=PARENT_ROLLUP))
            skill = parent
            hops += 1

    # 3. Transfer along typed relations, one hop only.
    relations = db.execute(select(SkillRelation)).scalars().all()
    for relation in relations:
        source = all_skills.get(relation.from_skill_id)
        target = all_skills.get(relation.to_skill_id)
        if source is None or target is None:
            continue
        if source.code in direct_codes:
            edges.append(
                SkillEdge(
                    source=source.code,
                    target=target.code,
                    relation=relation.relation,
                    weight=relation.weight,
                )
            )
            transferred = round(nodes[source.code].score * relation.weight, 4)
            current = nodes.get(target.code)
            if current is None or (not current.is_direct and current.score < transferred):
                nodes[target.code] = SkillNode(
                    code=target.code,
                    name=target.name,
                    skill_id=target.id,
                    score=transferred,
                    is_direct=False,
                    is_category=target.is_category,
                    derived_from=source.code,
                    derivation=(
                        f"partly transfers from {source.name} "
                        f"({int(relation.weight * 100)}% credit)"
                    ),
                )

    return SkillGraph(nodes=list(nodes.values()), edges=_dedupe_edges(edges))


def _dedupe_edges(edges: list[SkillEdge]) -> list[SkillEdge]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[SkillEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.relation)
        if key not in seen:
            seen.add(key)
            unique.append(edge)
    return unique


def effective_skill_scores(db: Session, beneficiary: BeneficiaryProfile) -> dict[str, float]:
    """Shorthand: code -> effective competence score in 0..1."""
    return build_skill_graph(db, beneficiary).score_map()


def build_target_graph(db: Session, qualification) -> dict:
    """Competency tree for a target qualification, for side-by-side display."""
    nodes = [
        {
            "code": qualification.code or qualification.id,
            "name": qualification.title,
            "type": "qualification",
            "nsqf_level": qualification.nsqf_level,
        }
    ]
    edges = []
    root = qualification.code or qualification.id
    for link in sorted(qualification.competency_links, key=lambda l: l.sequence):
        competency = link.competency
        if competency is None:
            continue
        nodes.append(
            {
                "code": competency.code,
                "name": competency.name,
                "type": "competency",
                "is_core": link.is_core,
                "nsqf_level": competency.nsqf_level,
                "nos_code": competency.nos_code,
            }
        )
        edges.append({"source": root, "target": competency.code, "relation": "requires"})
        for skill_link in competency.skill_links:
            if skill_link.skill is None:
                continue
            nodes.append(
                {
                    "code": skill_link.skill.code,
                    "name": skill_link.skill.name,
                    "type": "skill",
                    "coverage": skill_link.coverage,
                }
            )
            edges.append(
                {
                    "source": competency.code,
                    "target": skill_link.skill.code,
                    "relation": "evidenced_by",
                    "weight": skill_link.coverage,
                }
            )
    # De-duplicate nodes that appear under several competencies.
    unique: dict[str, dict] = {}
    for node in nodes:
        unique.setdefault(node["code"], node)
    return {"nodes": list(unique.values()), "edges": edges}
