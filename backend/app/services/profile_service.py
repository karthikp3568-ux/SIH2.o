"""Draft-profile assembly and commitment.

Extraction produces a *draft*. Nothing is written to the beneficiary's real
profile until they confirm it (or an admin corrects it), which is what makes
"AI assists the decision, it does not make it" true at the data layer rather
than just in the copy.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.enums import (
    EDUCATION_LABEL,
    EDUCATION_RANK,
    AuditAction,
    Confidence,
    EducationLevel,
    PROFICIENCY_SCORE,
    GoalType,
    Mobility,
    Proficiency,
    SkillSource,
    VerificationStatus,
)
from ..models import (
    BeneficiaryProfile,
    BeneficiarySkill,
    Constraint,
    Education,
    Experience,
    Goal,
    Interest,
    Location,
    Occupation,
    Skill,
    SkillEvidence,
    User,
    utcnow,
)
from . import audit
from .profile_extraction import ExtractionResult

EMPTY_DRAFT: dict[str, Any] = {
    "education": None,
    "occupations": [],
    #: Work the person said they stopped doing - kept, but never "current".
    "previous_occupations": [],
    "skills": [],
    "interests": [],
    "goals": [],
    "constraints": [],
    "mobility": None,
    "max_travel_km": None,
    "experience_years": None,
    "age": None,
    "target_income": None,
    "location": None,
    #: Facts a later answer contradicted, kept so the confirmation step can
    #: show what changed instead of silently overwriting it.
    "conflicts": [],
}


def new_draft() -> dict[str, Any]:
    return {
        key: ([] if isinstance(value, list) else None) for key, value in EMPTY_DRAFT.items()
    }


#: A newly stated fact at least this confident replaces an earlier one -
#: people correct themselves as they talk.
REPLACE_CONFIDENCE = 0.75


def _better(existing: dict | None, incoming: dict) -> bool:
    """Later statements win ties; a confident new statement is a correction."""
    if existing is None:
        return True
    incoming_confidence = incoming.get("confidence", 0)
    return incoming_confidence >= existing.get("confidence", 0) or incoming_confidence >= REPLACE_CONFIDENCE


def _replace_scalar(draft: dict[str, Any], key: str, incoming: dict) -> None:
    """Set a single-valued fact, recording a contradiction rather than hiding it."""
    existing = draft.get(key)
    if not _better(existing, incoming):
        return
    if existing and existing.get("value") != incoming.get("value") and existing.get("value") is not None:
        draft.setdefault("conflicts", []).append(
            {
                "field": key,
                "previous": existing.get("label") or existing.get("value"),
                "new": incoming.get("label") or incoming.get("value"),
            }
        )
    draft[key] = incoming


def merge_extraction(draft: dict[str, Any], extraction: ExtractionResult) -> dict[str, Any]:
    """Fold one turn's extraction into the running draft.

    Returns a new structure; the caller's input is never mutated in place.
    """
    draft = deepcopy({**new_draft(), **(draft or {})})

    if extraction.education:
        _replace_scalar(
            draft,
            "education",
            {
                **extraction.education.as_dict(),
                "label": EDUCATION_LABEL.get(str(extraction.education.value), str(extraction.education.value)),
            },
        )

    if extraction.mobility:
        _replace_scalar(draft, "mobility", extraction.mobility.as_dict())

    for key, fact in (
        ("max_travel_km", extraction.max_travel_km),
        ("experience_years", extraction.experience_years),
        ("age", extraction.age),
        ("target_income", extraction.target_income),
    ):
        if fact:
            _replace_scalar(draft, key, fact.as_dict())

    # "I stopped farming" moves farming out of current work; it is not lost.
    stopped = {o.value for o in extraction.previous_occupations}
    if stopped:
        known_previous = {o["value"] for o in draft["previous_occupations"]}
        for occupation in extraction.previous_occupations:
            if occupation.value not in known_previous:
                draft["previous_occupations"].append(occupation.as_dict())
                known_previous.add(occupation.value)
        draft["occupations"] = [o for o in draft["occupations"] if o["value"] not in stopped]

    existing_occupations = {o["value"] for o in draft["occupations"]}
    for occupation in extraction.occupations:
        if occupation.value not in existing_occupations:
            draft["occupations"].append(occupation.as_dict())
            existing_occupations.add(occupation.value)
            # Taking the work up again un-retires it.
            draft["previous_occupations"] = [
                o for o in draft["previous_occupations"] if o["value"] != occupation.value
            ]

    existing_interests = {i["value"] for i in draft["interests"]}
    for interest in extraction.interests:
        if interest.value not in existing_interests:
            draft["interests"].append(interest.as_dict())
            existing_interests.add(interest.value)

    existing_goals = {g["value"] for g in draft["goals"]}
    for goal in extraction.goals:
        if goal.value not in existing_goals:
            draft["goals"].append(goal.as_dict())
            existing_goals.add(goal.value)

    existing_constraints = {(c["kind"], c["value"]) for c in draft["constraints"]}
    for kind, fact in extraction.constraints:
        key = (kind, fact.value)
        if key not in existing_constraints:
            draft["constraints"].append({"kind": kind, **fact.as_dict()})
            existing_constraints.add(key)

    existing_skills = {s["code"]: s for s in draft["skills"]}
    for match in extraction.skills:
        known = existing_skills.get(match.code)
        if known is not None:
            # A later turn can strengthen an earlier claim ("I repair pumps" ->
            # "...for about five years"), but never weaken it.
            if PROFICIENCY_SCORE.get(match.proficiency, 0) > PROFICIENCY_SCORE.get(
                known.get("proficiency", ""), 0
            ):
                known["proficiency"] = match.proficiency
                known["confidence"] = match.confidence
            if match.years_experience and not known.get("years_experience"):
                known["years_experience"] = match.years_experience
                known["evidence"] = match.evidence
            continue
        draft["skills"].append(
            {
                "code": match.code,
                "name": match.name,
                "raw_label": match.raw_label,
                "proficiency": match.proficiency,
                "confidence": match.confidence,
                "source": match.source,
                "verification_status": match.verification_status,
                "years_experience": match.years_experience,
                "evidence": match.evidence,
                "is_category": match.is_category,
            }
        )
        existing_skills[match.code] = draft["skills"][-1]

    location = {}
    if extraction.pincode:
        location["pincode"] = extraction.pincode.value
    if extraction.district:
        location["district"] = extraction.district.value
    if extraction.state:
        location["state"] = extraction.state.value
    if location:
        draft["location"] = {**(draft.get("location") or {}), **location, "source": "conversation"}

    return draft


def filled_slots_from_draft(draft: dict[str, Any]) -> set[str]:
    """Which conversation slots the draft already answers."""
    filled: set[str] = set()
    if draft.get("education"):
        filled.add("education")
    if draft.get("occupations"):
        filled.add("occupation")
    if any(not s.get("is_category") for s in draft.get("skills", [])):
        filled.add("skills")
    if draft.get("interests"):
        filled.add("interests")
    if draft.get("goals"):
        filled.add("goal")
    if draft.get("mobility"):
        filled.add("mobility")
    if draft.get("experience_years"):
        filled.add("experience")
    location = draft.get("location") or {}
    if location.get("latitude") is not None or location.get("pincode") or location.get("district"):
        filled.add("location")
    return filled


# ---------------------------------------------------------------------------
# Commitment
# ---------------------------------------------------------------------------


def apply_draft(
    db: Session,
    beneficiary: BeneficiaryProfile,
    draft: dict[str, Any],
    *,
    actor: User | None = None,
    replace: bool = True,
    conversation_id: str | None = None,
) -> BeneficiaryProfile:
    """Write a confirmed draft onto the beneficiary's real profile.

    `replace=True` (the confirmation path) clears previously extracted rows so
    an edit genuinely removes a wrong fact rather than layering over it.
    Admin-verified skills are preserved regardless - a beneficiary re-running
    the conversation must not silently destroy verified evidence.
    """
    draft = {**new_draft(), **(draft or {})}
    now = utcnow()

    if replace:
        for education in list(beneficiary.educations):
            db.delete(education)
        for occupation in list(beneficiary.occupations):
            db.delete(occupation)
        for interest in list(beneficiary.interests):
            db.delete(interest)
        for goal in list(beneficiary.goals):
            db.delete(goal)
        for constraint in list(beneficiary.constraints):
            db.delete(constraint)
        for skill_link in list(beneficiary.skills):
            if skill_link.verification_status in {
                VerificationStatus.ADMIN_VERIFIED,
                VerificationStatus.ASSESSMENT_VERIFIED,
                VerificationStatus.CERTIFICATION_VERIFIED,
                VerificationStatus.TRAINING_VERIFIED,
            }:
                continue
            db.delete(skill_link)
        db.flush()
        # Reload collections from the database. Without this, deleted rows can
        # still be present on the in-session collections, and the held-skill
        # check below would wrongly treat them as already held.
        db.expire(beneficiary)

    education = draft.get("education")
    if education and education.get("value"):
        db.add(
            Education(
                beneficiary_id=beneficiary.id,
                level=str(education["value"]),
                source="conversation",
                confidence=_confidence_band(education.get("confidence", 0.7)),
                verification_status=VerificationStatus.SELF_DECLARED,
            )
        )

    for occupation in draft.get("occupations", []):
        db.add(
            Occupation(
                beneficiary_id=beneficiary.id,
                title=str(occupation["value"])[:160],
                is_current=True,
                source="conversation",
                confidence=_confidence_band(occupation.get("confidence", 0.7)),
            )
        )

    for interest in draft.get("interests", []):
        tag = str(interest["value"])
        db.add(
            Interest(
                beneficiary_id=beneficiary.id,
                label=tag.replace("_", " ").title(),
                tag=tag,
                strength=float(interest.get("confidence", 0.7)),
                source="conversation",
            )
        )

    for priority, goal in enumerate(draft.get("goals", []), start=1):
        value = str(goal["value"])
        if value not in {str(g) for g in GoalType}:
            continue
        db.add(
            Goal(
                beneficiary_id=beneficiary.id,
                goal_type=value,
                priority=priority,
                target_monthly_income_inr=(
                    int(draft["target_income"]["value"]) if draft.get("target_income") else None
                ),
                source="conversation",
            )
        )

    for constraint in draft.get("constraints", []):
        db.add(
            Constraint(
                beneficiary_id=beneficiary.id,
                kind=constraint.get("kind", "other"),
                label=str(constraint["value"])[:200],
                source="conversation",
            )
        )

    experience_years = draft.get("experience_years")
    skills_by_code = {s.code: s for s in db.execute(select(Skill)).scalars().all()}
    # Skills surviving the replace (admin/assessment verified) must not be re-added.
    held_codes = {link.skill.code for link in beneficiary.skills if link.skill is not None}

    for entry in draft.get("skills", []):
        code = entry.get("code")
        skill = skills_by_code.get(code)
        if skill is None or code in held_codes:
            continue
        link = BeneficiarySkill(
            beneficiary_id=beneficiary.id,
            skill_id=skill.id,
            raw_label=entry.get("raw_label") or skill.name,
            normalized_label=skill.name,
            proficiency=entry.get("proficiency") or Proficiency.BASIC,
            source=entry.get("source") or SkillSource.SELF_REPORTED,
            confidence=entry.get("confidence") or Confidence.MEDIUM,
            verification_status=entry.get("verification_status") or VerificationStatus.SELF_DECLARED,
            years_experience=entry.get("years_experience")
            or (experience_years.get("value") if experience_years else None),
        )
        db.add(link)
        db.flush()
        db.add(
            SkillEvidence(
                beneficiary_skill_id=link.id,
                evidence_type="conversation",
                description=entry.get("evidence") or "Stated during the conversation",
                reference=conversation_id,
                recorded_at=now,
            )
        )
        held_codes.add(code)

    if experience_years and experience_years.get("value"):
        db.add(
            Experience(
                beneficiary_id=beneficiary.id,
                title="Self-reported practical experience",
                years=float(experience_years["value"]),
                nature="practical",
                source="conversation",
                verification_status=VerificationStatus.SELF_DECLARED,
            )
        )

    mobility = draft.get("mobility")
    if mobility and str(mobility.get("value")) in {str(m) for m in Mobility}:
        beneficiary.mobility = str(mobility["value"])
    max_travel = draft.get("max_travel_km")
    if max_travel and max_travel.get("value"):
        beneficiary.max_travel_km = float(max_travel["value"])
    age = draft.get("age")
    if age and age.get("value"):
        beneficiary.age = int(age["value"])

    location = draft.get("location")
    if location:
        upsert_location(db, beneficiary, location)

    beneficiary.is_confirmed = True
    beneficiary.confirmed_at = now

    audit.record(
        db,
        action=AuditAction.PROFILE_CONFIRMED,
        actor=actor,
        entity_type="beneficiary_profile",
        entity_id=beneficiary.id,
        new_value={
            "education": (draft.get("education") or {}).get("value"),
            "skills": [s.get("code") for s in draft.get("skills", [])],
            "goals": [g.get("value") for g in draft.get("goals", [])],
            "mobility": beneficiary.mobility,
        },
        summary="Beneficiary confirmed the extracted profile",
    )
    db.commit()
    db.refresh(beneficiary)
    return beneficiary


def _confidence_band(score: float) -> str:
    if score >= 0.8:
        return Confidence.HIGH
    if score >= 0.55:
        return Confidence.MEDIUM
    return Confidence.LOW


def upsert_location(
    db: Session, beneficiary: BeneficiaryProfile, payload: dict[str, Any]
) -> Location:
    """Record a location with provenance; only one primary at a time."""
    for existing in beneficiary.locations:
        existing.is_primary = False
    location = Location(
        beneficiary_id=beneficiary.id,
        label=payload.get("label"),
        village=payload.get("village"),
        block=payload.get("block"),
        district=payload.get("district"),
        state=payload.get("state"),
        pincode=payload.get("pincode"),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        source=payload.get("source") or "manual",
        accuracy_m=payload.get("accuracy_m"),
        captured_at=utcnow(),
        is_primary=True,
    )
    db.add(location)
    db.flush()
    return location


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def profile_to_dict(beneficiary: BeneficiaryProfile) -> dict:
    location = beneficiary.primary_location
    educations = sorted(
        beneficiary.educations, key=lambda e: EDUCATION_RANK.get(e.level, 0), reverse=True
    )
    return {
        "id": beneficiary.id,
        "user_id": beneficiary.user_id,
        "display_name": beneficiary.display_name,
        "preferred_language": beneficiary.preferred_language,
        "age": beneficiary.age,
        "gender": beneficiary.gender,
        "mobility": beneficiary.mobility,
        "max_travel_km": beneficiary.max_travel_km,
        "is_confirmed": beneficiary.is_confirmed,
        "confirmed_at": beneficiary.confirmed_at.isoformat() if beneficiary.confirmed_at else None,
        "education": (
            {
                "level": educations[0].level,
                "label": EDUCATION_LABEL.get(educations[0].level, educations[0].level),
                "source": educations[0].source,
                "confidence": educations[0].confidence,
                "verification_status": educations[0].verification_status,
            }
            if educations
            else None
        ),
        "occupations": [
            {
                "id": o.id,
                "title": o.title,
                "sector": o.sector,
                "is_current": o.is_current,
                "source": o.source,
                "confidence": o.confidence,
            }
            for o in beneficiary.occupations
        ],
        "experiences": [
            {
                "id": e.id,
                "title": e.title,
                "years": e.years,
                "nature": e.nature,
                "verification_status": e.verification_status,
            }
            for e in beneficiary.experiences
        ],
        "skills": [
            {
                "id": s.id,
                "skill_id": s.skill_id,
                "code": s.skill.code if s.skill else None,
                "name": s.skill.name if s.skill else s.raw_label,
                "raw_label": s.raw_label,
                "proficiency": s.proficiency,
                "source": s.source,
                "confidence": s.confidence,
                "verification_status": s.verification_status,
                "years_experience": s.years_experience,
                "evidence": [
                    {"type": ev.evidence_type, "description": ev.description}
                    for ev in s.evidence
                ],
            }
            for s in beneficiary.skills
            if s.is_active
        ],
        "interests": [
            {"id": i.id, "label": i.label, "tag": i.tag, "strength": i.strength}
            for i in beneficiary.interests
        ],
        "goals": [
            {
                "id": g.id,
                "goal_type": g.goal_type,
                "description": g.description,
                "target_monthly_income_inr": g.target_monthly_income_inr,
                "priority": g.priority,
            }
            for g in beneficiary.goals
            if g.is_active
        ],
        "constraints": [
            {"id": c.id, "kind": c.kind, "label": c.label, "severity": c.severity}
            for c in beneficiary.constraints
        ],
        "location": (
            {
                "id": location.id,
                "label": location.label,
                "village": location.village,
                "block": location.block,
                "district": location.district,
                "state": location.state,
                "pincode": location.pincode,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "source": location.source,
                "accuracy_m": location.accuracy_m,
                "captured_at": location.captured_at.isoformat() if location.captured_at else None,
            }
            if location
            else None
        ),
    }


def validate_education_value(value: str) -> str:
    if value not in {str(e) for e in EducationLevel}:
        raise ValueError(f"Unknown education level: {value}")
    return value
