"""Database seeding.

Loads the taxonomy, recognised-qualification records and verified demo
opportunities, creates the demo accounts, and builds the RAG index. Safe to run
repeatedly: every record is matched on its natural key and updated in place.

Dates in the seed files are expressed as offsets ("last_verified_days_ago") and
resolved at load time, so a checked-out repository never demonstrates freshness
filtering with data that has silently gone stale.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.enums import Mobility, RecordStatus, Role, VerificationStatus
from ..models import (
    Base,
    BeneficiaryProfile,
    Competency,
    CompetencySkill,
    Consent,
    Opportunity,
    Qualification,
    QualificationCompetency,
    Skill,
    SkillAlias,
    SkillRelation,
    TrainingProgram,
    User,
    utcnow,
)
from ..providers.data_sources import load_seed_file
from ..security import hash_password

logger = logging.getLogger(__name__)
settings = get_settings()

#: Ravi's home village, used by the demo flow.
DEMO_LOCATION = {
    "label": "Wadgaon, Sinnar taluka",
    "village": "Wadgaon",
    "block": "Sinnar",
    "district": "Nashik",
    "state": "Maharashtra",
    "pincode": "422103",
    "latitude": 19.8500,
    "longitude": 74.0000,
    "source": "demo_seed",
}


def _offset(days: int | None):
    return utcnow() + timedelta(days=days) if days is not None else None


def _ago(days: int | None):
    return utcnow() - timedelta(days=days) if days is not None else None


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


def seed_skills(db: Session) -> dict[str, Skill]:
    records = load_seed_file("skills.json")
    by_code: dict[str, Skill] = {
        s.code: s for s in db.execute(select(Skill)).scalars().all()
    }

    # First pass: rows without parents so foreign keys always resolve.
    for record in records:
        skill = by_code.get(record["code"])
        if skill is None:
            skill = Skill(code=record["code"], name=record["name"])
            db.add(skill)
            by_code[record["code"]] = skill
        skill.name = record["name"]
        skill.description = record.get("description")
        skill.sector = record.get("sector")
        skill.is_category = bool(record.get("is_category", False))
        skill.is_active = True
    db.flush()

    for record in records:
        parent_code = record.get("parent")
        if parent_code:
            by_code[record["code"]].parent_id = by_code[parent_code].id
    db.flush()

    existing_aliases = {
        (a.skill_id, a.alias.lower())
        for a in db.execute(select(SkillAlias)).scalars().all()
    }
    for record in records:
        skill = by_code[record["code"]]
        for alias in record.get("aliases", []):
            key = (skill.id, alias["alias"].lower())
            if key in existing_aliases:
                continue
            db.add(
                SkillAlias(
                    skill_id=skill.id,
                    alias=alias["alias"],
                    language=alias.get("language", "en"),
                )
            )
            existing_aliases.add(key)
    db.flush()
    return by_code


def seed_skill_relations(db: Session, skills: dict[str, Skill]) -> None:
    existing = {
        (r.from_skill_id, r.to_skill_id, r.relation)
        for r in db.execute(select(SkillRelation)).scalars().all()
    }
    for record in load_seed_file("skill_relations.json"):
        source, target = skills.get(record["from"]), skills.get(record["to"])
        if source is None or target is None:
            logger.warning("Skipping skill relation with unknown code: %s", record)
            continue
        key = (source.id, target.id, record.get("relation", "related_to"))
        if key in existing:
            continue
        db.add(
            SkillRelation(
                from_skill_id=source.id,
                to_skill_id=target.id,
                relation=record.get("relation", "related_to"),
                weight=float(record.get("weight", 0.5)),
            )
        )
        existing.add(key)
    db.flush()


def seed_competencies(db: Session, skills: dict[str, Skill]) -> dict[str, Competency]:
    by_code = {c.code: c for c in db.execute(select(Competency)).scalars().all()}
    for record in load_seed_file("competencies.json"):
        competency = by_code.get(record["code"])
        if competency is None:
            competency = Competency(code=record["code"], name=record["name"])
            db.add(competency)
            by_code[record["code"]] = competency
        competency.name = record["name"]
        competency.description = record.get("description")
        competency.nos_code = record.get("nos_code")
        competency.sector = record.get("sector")
        competency.nsqf_level = record.get("nsqf_level")
        competency.status = record.get("status", RecordStatus.ACTIVE)
    db.flush()

    existing_links = {
        (link.competency_id, link.skill_id)
        for link in db.execute(select(CompetencySkill)).scalars().all()
    }
    for record in load_seed_file("competencies.json"):
        competency = by_code[record["code"]]
        for mapping in record.get("skills", []):
            skill = skills.get(mapping["code"])
            if skill is None:
                logger.warning("Competency %s references unknown skill %s", record["code"], mapping["code"])
                continue
            if (competency.id, skill.id) in existing_links:
                continue
            db.add(
                CompetencySkill(
                    competency_id=competency.id,
                    skill_id=skill.id,
                    coverage=float(mapping.get("coverage", 1.0)),
                )
            )
            existing_links.add((competency.id, skill.id))
    db.flush()
    return by_code


def seed_qualifications(db: Session, competencies: dict[str, Competency]) -> dict[str, Qualification]:
    by_code = {
        q.code: q for q in db.execute(select(Qualification)).scalars().all() if q.code
    }
    for record in load_seed_file("qualifications.json"):
        qualification = by_code.get(record["code"])
        if qualification is None:
            qualification = Qualification(
                code=record["code"],
                title=record["title"],
                occupation_role=record["occupation_role"],
                sector=record["sector"],
                source=record["source"],
            )
            db.add(qualification)
            by_code[record["code"]] = qualification
        qualification.title = record["title"]
        qualification.occupation_role = record["occupation_role"]
        qualification.sector = record["sector"]
        qualification.sub_sector = record.get("sub_sector")
        qualification.nsqf_level = record.get("nsqf_level")
        qualification.description = record.get("description")
        qualification.minimum_education = record.get("minimum_education")
        qualification.typical_duration_hours = record.get("typical_duration_hours")
        qualification.status = record.get("status", RecordStatus.ACTIVE)
        qualification.source = record["source"]
        qualification.source_url = record.get("source_url")
        qualification.version = record.get("version")
        qualification.superseded_by_code = record.get("superseded_by_code")
        qualification.last_verified_at = _ago(record.get("last_verified_days_ago"))
        qualification.valid_until = _offset(record.get("valid_until_days"))
    db.flush()

    existing_links = {
        (link.qualification_id, link.competency_id)
        for link in db.execute(select(QualificationCompetency)).scalars().all()
    }
    for record in load_seed_file("qualifications.json"):
        qualification = by_code[record["code"]]
        for mapping in record.get("competencies", []):
            competency = competencies.get(mapping["code"])
            if competency is None:
                logger.warning(
                    "Qualification %s references unknown competency %s",
                    record["code"],
                    mapping["code"],
                )
                continue
            if (qualification.id, competency.id) in existing_links:
                continue
            db.add(
                QualificationCompetency(
                    qualification_id=qualification.id,
                    competency_id=competency.id,
                    is_core=bool(mapping.get("is_core", True)),
                    sequence=int(mapping.get("sequence", 0)),
                    weight=float(mapping.get("weight", 1.0)),
                )
            )
            existing_links.add((qualification.id, competency.id))
    db.flush()
    return by_code


def seed_opportunities(db: Session, qualifications: dict[str, Qualification]) -> int:
    existing = {
        o.external_id: o
        for o in db.execute(select(Opportunity)).scalars().all()
        if o.external_id
    }
    count = 0
    for record in load_seed_file("opportunities.json"):
        opportunity = existing.get(record["external_id"])
        if opportunity is None:
            opportunity = Opportunity(
                external_id=record["external_id"],
                title=record["title"],
                provider=record["provider"],
                opportunity_type=record["opportunity_type"],
                description=record["description"],
                source=record["source"],
            )
            db.add(opportunity)
            existing[record["external_id"]] = opportunity
            count += 1

        qualification = qualifications.get(record.get("qualification_code") or "")
        opportunity.title = record["title"]
        opportunity.provider = record["provider"]
        opportunity.opportunity_type = record["opportunity_type"]
        opportunity.description = record["description"]
        opportunity.sector = record.get("sector")
        opportunity.qualification_id = qualification.id if qualification else None
        opportunity.skills_required = record.get("skills_required", [])
        opportunity.skill_codes = record.get("skill_codes", [])
        opportunity.competencies_required = record.get("competencies_required", [])
        opportunity.education_required = record.get("education_required")
        opportunity.min_age = record.get("min_age")
        opportunity.max_age = record.get("max_age")
        opportunity.eligibility_notes = record.get("eligibility_notes")
        opportunity.eligibility_rules = record.get("eligibility_rules", {})
        opportunity.location_label = record.get("location_label")
        opportunity.village = record.get("village")
        opportunity.block = record.get("block")
        opportunity.district = record.get("district")
        opportunity.state = record.get("state")
        opportunity.pincode = record.get("pincode")
        opportunity.latitude = record.get("latitude")
        opportunity.longitude = record.get("longitude")
        opportunity.mobility_required = record.get("mobility_required", Mobility.LOW)
        opportunity.stipend_or_income_inr = record.get("stipend_or_income_inr")
        opportunity.seats_total = record.get("seats_total")
        opportunity.seats_available = record.get("seats_available")
        opportunity.source = record["source"]
        opportunity.source_url = record.get("source_url")
        opportunity.ingestion_channel = "seed"
        opportunity.source_trust = float(record.get("source_trust", 0.6))
        opportunity.verification_status = record.get(
            "verification_status", VerificationStatus.UNVERIFIED
        )
        opportunity.status = record.get("status", RecordStatus.ACTIVE)
        opportunity.last_verified_at = _ago(record.get("last_verified_days_ago"))
        opportunity.valid_until = _offset(record.get("valid_until_days"))
        opportunity.valid_from = _offset(record.get("valid_from_days"))
        db.flush()

        program_record = record.get("training_program")
        if program_record:
            program = opportunity.training_program or TrainingProgram(
                opportunity_id=opportunity.id
            )
            program.training_centre = program_record.get("training_centre")
            program.duration_hours = program_record.get("duration_hours")
            program.duration_weeks = program_record.get("duration_weeks")
            program.mode = program_record.get("mode", "in_person")
            program.fee_inr = program_record.get("fee_inr")
            program.is_subsidised = bool(program_record.get("is_subsidised", False))
            program.funding_notes = program_record.get("funding_notes")
            program.batch_start_date = _offset(program_record.get("batch_start_days"))
            program.batch_end_date = _offset(program_record.get("batch_end_days"))
            program.certification_offered = program_record.get("certification_offered")
            program.languages_of_instruction = program_record.get(
                "languages_of_instruction", []
            )
            if program.id is None:
                db.add(program)
    db.flush()
    return count


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def _upsert_user(
    db: Session, email: str, name: str, password: str, role: str, language: str = "en"
) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            role=role,
            preferred_language=language,
        )
        db.add(user)
        db.flush()
    else:
        user.full_name = name
        user.role = role
    return user


def seed_users(db: Session) -> dict[str, User]:
    admin = _upsert_user(
        db,
        settings.demo_admin_email,
        "Demo Administrator",
        settings.demo_admin_password,
        Role.ADMIN,
    )
    beneficiary_user = _upsert_user(
        db,
        settings.demo_beneficiary_email,
        "Ravi",
        settings.demo_beneficiary_password,
        Role.BENEFICIARY,
        language="mr",
    )
    counsellor = _upsert_user(
        db, "counsellor@navigator.example.com", "Demo Counsellor", settings.demo_admin_password, Role.COUNSELLOR
    )
    provider = _upsert_user(
        db, "provider@navigator.example.com", "Demo Training Provider", settings.demo_admin_password, Role.PROVIDER
    )

    profile = db.execute(
        select(BeneficiaryProfile).where(BeneficiaryProfile.user_id == beneficiary_user.id)
    ).scalar_one_or_none()
    if profile is None:
        profile = BeneficiaryProfile(
            user_id=beneficiary_user.id,
            display_name="Ravi",
            preferred_language="mr",
            age=29,
            mobility=Mobility.LOW,
        )
        db.add(profile)
        db.flush()

    # Consent rows exist so the demo account can be used without re-prompting;
    # a real registration collects these explicitly.
    for purpose in ("voice_processing", "profile_processing", "location_processing", "outcome_tracking"):
        existing = db.execute(
            select(Consent).where(Consent.user_id == beneficiary_user.id, Consent.purpose == purpose)
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                Consent(
                    user_id=beneficiary_user.id,
                    purpose=purpose,
                    granted=True,
                    granted_at=utcnow(),
                    notes="Granted during demo seeding",
                )
            )
    db.flush()
    return {
        "admin": admin,
        "beneficiary": beneficiary_user,
        "counsellor": counsellor,
        "provider": provider,
    }


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


#: Nullable columns added after the initial schema. `create_all` never alters
#: an existing table, so a database created earlier gets them here; Alembic
#: revision 3c1f2a7b9d10 carries the same change for migrated deployments.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("conversation_messages", "client_message_id", "VARCHAR(64)"),
    ("conversation_messages", "response_snapshot", "JSON"),
]
_ADDITIVE_INDEXES: list[tuple[str, str, str]] = [
    (
        "ix_message_conversation_client_id",
        "conversation_messages",
        "conversation_id, client_message_id",
    ),
]


def create_all_tables(engine) -> None:
    from sqlalchemy import inspect, text  # noqa: PLC0415

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, column, sql_type in _ADDITIVE_COLUMNS:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
                logger.info("Added column %s.%s", table, column)
        for name, table, columns in _ADDITIVE_INDEXES:
            if name not in {i["name"] for i in inspector.get_indexes(table)}:
                connection.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} ({columns})"))


def seed_database(db: Session, *, build_index: bool = True) -> dict:
    """Idempotently load every seed record. Returns a summary."""
    skills = seed_skills(db)
    seed_skill_relations(db, skills)
    competencies = seed_competencies(db, skills)
    qualifications = seed_qualifications(db, competencies)
    new_opportunities = seed_opportunities(db, qualifications)
    users = seed_users(db)
    db.commit()

    index_report = None
    if build_index:
        from ..rag.ingest import sync_knowledge_base  # noqa: PLC0415 - avoids a cycle

        index_report = sync_knowledge_base(db).as_dict()

    summary = {
        "skills": len(skills),
        "competencies": len(competencies),
        "qualifications": len(qualifications),
        "opportunities_created": new_opportunities,
        "users": sorted(users),
        "knowledge_index": index_report,
    }
    logger.info("Seeding complete: %s", summary)
    return summary
