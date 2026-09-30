"""RAG ingestion pipeline.

Knowledge documents are generated from the structured records the system
already holds (opportunities, qualifications) plus authored guidance text. Each
chunk keeps a back-link to the row it came from (`entity_type` / `entity_id`),
so anything retrieved can be resolved to a verifiable record with a source and
a verification date. That back-link is what makes grounding checkable rather
than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.enums import RecordStatus
from ..models import (
    KnowledgeChunk,
    KnowledgeDocument,
    Opportunity,
    Qualification,
    utcnow,
)
from ..providers.data_sources import load_seed_file
from ..providers.embeddings import get_embedding_provider
from .chunking import chunk_text, content_hash, estimate_tokens


@dataclass
class IngestionReport:
    documents_created: int = 0
    documents_updated: int = 0
    documents_unchanged: int = 0
    documents_retired: int = 0
    chunks_written: int = 0
    embedding_provider: str = ""

    def as_dict(self) -> dict:
        return {
            "documents_created": self.documents_created,
            "documents_updated": self.documents_updated,
            "documents_unchanged": self.documents_unchanged,
            "documents_retired": self.documents_retired,
            "chunks_written": self.chunks_written,
            "embedding_provider": self.embedding_provider,
        }


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------


def build_opportunity_text(opportunity: Opportunity) -> str:
    """Flatten an opportunity into retrievable prose.

    Field labels are included ("Skills needed:") because they make the chunk
    readable on its own when shown as evidence in the admin UI.
    """
    parts = [
        f"{opportunity.title}. Offered by {opportunity.provider}.",
        f"Type of opportunity: {opportunity.opportunity_type.replace('_', ' ')}.",
        opportunity.description or "",
    ]
    if opportunity.skills_required:
        parts.append("Skills needed: " + ", ".join(opportunity.skills_required) + ".")
    if opportunity.qualification is not None:
        qualification = opportunity.qualification
        parts.append(
            f"Linked qualification: {qualification.title}"
            + (f" ({qualification.code})" if qualification.code else "")
            + (f", NSQF level {qualification.nsqf_level}" if qualification.nsqf_level else "")
            + f", occupational role {qualification.occupation_role}."
        )
    if opportunity.education_required:
        parts.append(f"Minimum education: {opportunity.education_required.replace('_', ' ')}.")
    if opportunity.eligibility_notes:
        parts.append(f"Eligibility: {opportunity.eligibility_notes}")
    location = ", ".join(
        p for p in (opportunity.location_label, opportunity.district, opportunity.state) if p
    )
    if location:
        parts.append(f"Location: {location}.")
    if opportunity.stipend_or_income_inr:
        parts.append(f"Indicative monthly income or stipend: Rs {opportunity.stipend_or_income_inr}.")
    if opportunity.training_program is not None:
        program = opportunity.training_program
        detail = []
        if program.duration_hours:
            detail.append(f"{program.duration_hours} hours")
        if program.duration_weeks:
            detail.append(f"about {program.duration_weeks} weeks")
        if program.fee_inr is not None:
            detail.append("no fee" if program.fee_inr == 0 else f"fee Rs {program.fee_inr}")
        if program.certification_offered:
            detail.append(f"leads to: {program.certification_offered}")
        if detail:
            parts.append("Training details: " + "; ".join(detail) + ".")
    return "\n".join(p for p in parts if p)


def build_qualification_text(qualification: Qualification) -> str:
    parts = [
        f"{qualification.title}"
        + (f" ({qualification.code})" if qualification.code else "")
        + f". Occupational role: {qualification.occupation_role}.",
        f"Sector: {qualification.sector}."
        + (f" Sub-sector: {qualification.sub_sector}." if qualification.sub_sector else ""),
    ]
    if qualification.nsqf_level:
        parts.append(f"NSQF level {qualification.nsqf_level}.")
    if qualification.minimum_education:
        parts.append(
            f"Minimum education to enter: {qualification.minimum_education.replace('_', ' ')}."
        )
    if qualification.description:
        parts.append(qualification.description)
    competencies = [
        f"{link.competency.name}"
        + (f" [{link.competency.nos_code}]" if link.competency.nos_code else "")
        + ("" if link.is_core else " (elective)")
        for link in sorted(qualification.competency_links, key=lambda l: l.sequence)
        if link.competency is not None
    ]
    if competencies:
        parts.append("Competencies required: " + "; ".join(competencies) + ".")
    if qualification.typical_duration_hours:
        parts.append(f"Typical training duration: {qualification.typical_duration_hours} hours.")
    parts.append(f"Status: {qualification.status}. Source: {qualification.source}.")
    if qualification.status == RecordStatus.RETIRED and qualification.superseded_by_code:
        parts.append(f"This standard is retired and superseded by {qualification.superseded_by_code}.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def _upsert_document(
    db: Session,
    *,
    entity_type: str,
    entity_id: str | None,
    title: str,
    doc_type: str,
    source: str,
    text: str,
    metadata: dict,
    language: str = "en",
    source_url: str | None = None,
    source_authority: str | None = None,
    status: str = RecordStatus.ACTIVE,
    last_verified_at=None,
    sector: str | None = None,
    nsqf_level: int | None = None,
    district: str | None = None,
    state: str | None = None,
    report: IngestionReport | None = None,
    embed: bool = True,
) -> KnowledgeDocument:
    digest = content_hash(text)
    existing = None
    if entity_id:
        existing = db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.entity_type == entity_type,
                KnowledgeDocument.entity_id == entity_id,
            )
        ).scalar_one_or_none()
    else:
        existing = db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.entity_type == entity_type, KnowledgeDocument.title == title
            )
        ).scalar_one_or_none()

    if existing is not None and existing.content_hash == digest and existing.status == status:
        # Metadata that can change without changing the text still refreshes.
        existing.last_verified_at = last_verified_at or existing.last_verified_at
        if report:
            report.documents_unchanged += 1
        return existing

    if existing is None:
        document = KnowledgeDocument(
            title=title,
            doc_type=doc_type,
            source=source,
            source_url=source_url,
            source_authority=source_authority,
            language=language,
            status=status,
            last_verified_at=last_verified_at,
            entity_type=entity_type,
            entity_id=entity_id,
            doc_metadata=metadata,
            content_hash=digest,
        )
        db.add(document)
        db.flush()
        if report:
            report.documents_created += 1
    else:
        document = existing
        document.title = title
        document.source = source
        document.source_url = source_url
        document.source_authority = source_authority
        document.status = status
        document.last_verified_at = last_verified_at
        document.doc_metadata = metadata
        document.content_hash = digest
        for chunk in list(document.chunks):
            db.delete(chunk)
        db.flush()
        if report:
            report.documents_updated += 1

    pieces = chunk_text(text)
    provider = get_embedding_provider()
    vectors = provider.embed(pieces) if (embed and pieces) else [None] * len(pieces)
    for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                sequence=index,
                text=piece,
                sector=sector,
                nsqf_level=nsqf_level,
                district=district,
                state=state,
                status=status,
                chunk_metadata=metadata,
                embedding=vector,
                embedding_model=provider.name if vector else None,
                embedding_dim=provider.dim if vector else None,
                token_estimate=estimate_tokens(piece),
            )
        )
        if report:
            report.chunks_written += 1
    return document


def ingest_opportunity(db: Session, opportunity: Opportunity, report: IngestionReport | None = None, embed: bool = True) -> None:
    """(Re)index a single opportunity. Called after create/update in the admin API."""
    metadata = {
        "entity": "opportunity",
        "opportunity_type": opportunity.opportunity_type,
        "sector": opportunity.sector,
        "district": opportunity.district,
        "state": opportunity.state,
        "education_required": opportunity.education_required,
        "mobility_required": opportunity.mobility_required,
        "qualification_code": opportunity.qualification.code if opportunity.qualification else None,
        "nsqf_level": opportunity.qualification.nsqf_level if opportunity.qualification else None,
        "verification_status": opportunity.verification_status,
        "source_trust": opportunity.source_trust,
    }
    _upsert_document(
        db,
        entity_type="opportunity",
        entity_id=opportunity.id,
        title=opportunity.title,
        doc_type="opportunity",
        source=opportunity.source,
        source_url=opportunity.source_url,
        text=build_opportunity_text(opportunity),
        metadata=metadata,
        status=opportunity.status,
        last_verified_at=opportunity.last_verified_at,
        sector=opportunity.sector,
        nsqf_level=metadata["nsqf_level"],
        district=opportunity.district,
        state=opportunity.state,
        report=report,
        embed=embed,
    )


def ingest_qualification(db: Session, qualification: Qualification, report: IngestionReport | None = None, embed: bool = True) -> None:
    metadata = {
        "entity": "qualification",
        "qualification_code": qualification.code,
        "sector": qualification.sector,
        "nsqf_level": qualification.nsqf_level,
        "minimum_education": qualification.minimum_education,
        "status": qualification.status,
        "occupation_role": qualification.occupation_role,
    }
    _upsert_document(
        db,
        entity_type="qualification",
        entity_id=qualification.id,
        title=qualification.title,
        doc_type="qualification",
        source=qualification.source,
        source_url=qualification.source_url,
        source_authority=qualification.source,
        text=build_qualification_text(qualification),
        metadata=metadata,
        status=qualification.status,
        last_verified_at=qualification.last_verified_at,
        sector=qualification.sector,
        nsqf_level=qualification.nsqf_level,
        report=report,
        embed=embed,
    )


def ingest_guidance(db: Session, report: IngestionReport | None = None, embed: bool = True) -> None:
    """Authored guidance text - process explanation, not opportunity claims."""
    for record in load_seed_file("guidance_documents.json"):
        _upsert_document(
            db,
            entity_type="guidance",
            entity_id=None,
            title=record["title"],
            doc_type=record.get("doc_type", "guidance"),
            source=record["source"],
            text=record["text"],
            metadata=record.get("metadata", {}),
            language=record.get("language", "en"),
            sector=record.get("sector"),
            last_verified_at=utcnow(),
            report=report,
            embed=embed,
        )


def sync_knowledge_base(db: Session, embed: bool = True) -> IngestionReport:
    """Rebuild the knowledge store from the current structured records."""
    report = IngestionReport(embedding_provider=get_embedding_provider().name)

    opportunities = (
        db.execute(
            select(Opportunity).options(
                selectinload(Opportunity.qualification),
                selectinload(Opportunity.training_program),
            )
        )
        .scalars()
        .all()
    )
    for opportunity in opportunities:
        ingest_opportunity(db, opportunity, report, embed=embed)

    qualifications = (
        db.execute(
            select(Qualification).options(
                selectinload(Qualification.competency_links)
            )
        )
        .scalars()
        .all()
    )
    for qualification in qualifications:
        ingest_qualification(db, qualification, report, embed=embed)

    ingest_guidance(db, report, embed=embed)

    # Any document whose backing row disappeared is retired, never left live.
    live_ids = {o.id for o in opportunities} | {q.id for q in qualifications}
    orphans = (
        db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.entity_type.in_(["opportunity", "qualification"]),
                KnowledgeDocument.status != RecordStatus.RETIRED,
            )
        )
        .scalars()
        .all()
    )
    for document in orphans:
        if document.entity_id not in live_ids:
            document.status = RecordStatus.RETIRED
            for chunk in document.chunks:
                chunk.status = RecordStatus.RETIRED
            report.documents_retired += 1

    db.commit()
    return report
