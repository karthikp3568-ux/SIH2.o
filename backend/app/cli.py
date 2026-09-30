"""Command line utilities.

    python -m app.cli seed                  # create tables + load seed data + build index
    python -m app.cli reindex               # rebuild the RAG index only
    python -m app.cli import-opportunities data.csv [--commit]
    python -m app.cli demo                  # run the Ravi walkthrough end to end
    python -m app.cli reset --yes           # drop and recreate every table
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from .db import SessionLocal, engine
from .models import Base, BeneficiaryProfile, User
from .providers.data_sources import CsvOpportunityProvider
from .rag.ingest import sync_knowledge_base
from .seed.seed_data import DEMO_LOCATION, create_all_tables, seed_database


def cmd_seed(_: argparse.Namespace) -> int:
    create_all_tables(engine)
    with SessionLocal() as db:
        summary = seed_database(db)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_reindex(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        print(json.dumps(sync_knowledge_base(db).as_dict(), indent=2))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    provider = CsvOpportunityProvider(args.path)
    try:
        records = provider.fetch()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    print(f"Read {len(records)} row(s) from {args.path}")
    if not args.commit:
        print("Dry run. Re-run with --commit to write these records.")
        for record in records[:5]:
            print("  -", record.get("external_id"), record.get("title"))
        return 0

    from .core.enums import RecordStatus, VerificationStatus  # noqa: PLC0415
    from .models import Opportunity, utcnow  # noqa: PLC0415
    from .services.skill_normalization import normalize_labels  # noqa: PLC0415

    created = updated = 0
    with SessionLocal() as db:
        existing = {
            o.external_id: o
            for o in db.execute(select(Opportunity)).scalars().all()
            if o.external_id
        }
        for record in records:
            external_id = record.get("external_id")
            target = existing.get(external_id) if external_id else None
            if target is None:
                target = Opportunity(
                    external_id=external_id,
                    title=record["title"],
                    provider=record["provider"],
                    opportunity_type=record["opportunity_type"],
                    description=record["description"],
                    source=record["source"],
                )
                db.add(target)
                created += 1
            else:
                updated += 1
            for field, value in record.items():
                if field != "external_id" and hasattr(target, field):
                    setattr(target, field, value)
            target.ingestion_channel = "csv_import"
            target.verification_status = VerificationStatus.UNVERIFIED
            target.status = record.get("status", RecordStatus.DRAFT)
            target.last_verified_at = target.last_verified_at or utcnow()
            if record.get("skills_required"):
                target.skill_codes, _ = normalize_labels(db, record["skills_required"])
        db.commit()
        sync_knowledge_base(db)
    print(f"Created {created}, updated {updated}. Imported records start as DRAFT and UNVERIFIED.")
    return 0


def cmd_demo(_: argparse.Namespace) -> int:
    """Run the Ravi walkthrough headlessly and print each stage."""
    from .api.demo import RAVI_SCRIPT  # noqa: PLC0415
    from .config import get_settings  # noqa: PLC0415
    from .services import profile_service  # noqa: PLC0415
    from .services.conversation_engine import handle_message, start_conversation  # noqa: PLC0415
    from .services.recommendation import generate_recommendations  # noqa: PLC0415
    from .services.skill_gap import analyze_gap  # noqa: PLC0415
    from .services.skill_graph import build_skill_graph  # noqa: PLC0415

    settings = get_settings()
    create_all_tables(engine)
    with SessionLocal() as db:
        seed_database(db)
        user = db.execute(
            select(User).where(User.email == settings.demo_beneficiary_email)
        ).scalar_one()
        profile = db.execute(
            select(BeneficiaryProfile).where(BeneficiaryProfile.user_id == user.id)
        ).scalar_one()

        # apply_draft(replace=True) clears the extracted rows itself; only the
        # location needs resetting here, since speech cannot supply one.
        for row in list(profile.locations):
            db.delete(row)
        db.flush()
        profile_service.upsert_location(db, profile, DEMO_LOCATION)
        db.commit()

        conversation, greeting = start_conversation(db, profile, language="en")
        print(f"\nASSISTANT: {greeting}")
        for line in RAVI_SCRIPT:
            print(f"\nRAVI: {line['text']}")
            result = handle_message(db, conversation, line["text"])
            print(f"ASSISTANT: {result.assistant_message}")
            if result.newly_filled:
                print(f"   [captured: {', '.join(result.newly_filled)}]")

        profile_service.apply_draft(db, profile, conversation.draft_profile, actor=user)
        print("\n--- EXTRACTED PROFILE ---")
        summary = profile_service.profile_to_dict(profile)
        print(f"Education : {(summary['education'] or {}).get('label')}")
        print(f"Occupation: {', '.join(o['title'] for o in summary['occupations'])}")
        print("Skills    : " + ", ".join(
            f"{s['name']} ({s['proficiency']}, {s['verification_status']})"
            for s in summary["skills"]
        ))
        print(f"Interests : {', '.join(i['label'] for i in summary['interests'])}")
        print(f"Goals     : {', '.join(g['goal_type'] for g in summary['goals'])}")
        print(f"Mobility  : {summary['mobility']}")

        graph = build_skill_graph(db, profile)
        print("\n--- SKILL GRAPH ---")
        for node in sorted(graph.nodes, key=lambda n: -n.score)[:10]:
            marker = "direct" if node.is_direct else (node.derivation or "derived")
            print(f"  {node.name:<34} {node.score:.2f}  ({marker})")

        for mobility in ("low", "high"):
            profile.mobility = mobility
            db.commit()
            result = generate_recommendations(db, profile, actor=user)
            print(f"\n--- TOP PATHWAYS (mobility = {mobility}) ---")
            if result.no_match:
                print(f"  {result.no_match.message}")
                continue
            for recommendation in sorted(result.run.recommendations, key=lambda r: r.rank):
                distance = (
                    f"{recommendation.distance_km:.0f} km"
                    if recommendation.distance_km is not None
                    else "distance unknown"
                )
                print(
                    f"  {recommendation.rank}. {recommendation.opportunity.title}\n"
                    f"     score {recommendation.match_score:.2f} | {distance} | "
                    f"skill fit {recommendation.skill_fit_band} | gap {recommendation.skill_gap_band}"
                )
                for reason in sorted(recommendation.reasons, key=lambda r: r.sequence):
                    if reason.category == "why_fits":
                        print(f"       + {reason.label}")

        top = sorted(result.run.recommendations, key=lambda r: r.rank)[0]
        if top.qualification is not None:
            report = analyze_gap(db, profile, top.qualification, build_skill_graph(db, profile))
            print(f"\n--- SKILL GAP vs {top.qualification.title} ---")
            print(f"  Covered {int(report.coverage_ratio * 100)}%, gap is {report.gap_band}")
            for competency in report.covered:
                print(f"    [have]    {competency.name}")
            for competency in report.partial:
                print(f"    [partial] {competency.name}")
            for competency in report.missing:
                print(f"    [need]    {competency.name}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to drop tables without --yes", file=sys.stderr)
        return 1
    Base.metadata.drop_all(bind=engine)
    create_all_tables(engine)
    with SessionLocal() as db:
        seed_database(db)
    print("Database reset and reseeded.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="create tables and load seed data").set_defaults(func=cmd_seed)
    sub.add_parser("reindex", help="rebuild the RAG index").set_defaults(func=cmd_reindex)
    sub.add_parser("demo", help="run the Ravi walkthrough").set_defaults(func=cmd_demo)

    importer = sub.add_parser("import-opportunities", help="import opportunities from CSV")
    importer.add_argument("path")
    importer.add_argument("--commit", action="store_true", help="write the records")
    importer.set_defaults(func=cmd_import)

    reset = sub.add_parser("reset", help="drop and recreate all tables")
    reset.add_argument("--yes", action="store_true")
    reset.set_defaults(func=cmd_reset)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
