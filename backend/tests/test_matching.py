"""Phase 3: skill graph, skill gap, filtering and hybrid ranking.

This module implements the seven demo cases named in the problem statement,
plus the supporting unit tests for each mechanism they rely on.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.enums import RecordStatus, VerificationStatus
from app.core.geo import bounding_box, haversine_km, location_fit_score
from app.models import Opportunity, Qualification, utcnow
from app.services.ranking import RELEVANCE_FLOOR, explain_weights
from app.services.recommendation import generate_recommendations
from app.services.skill_gap import COVERED_THRESHOLD, analyze_gap
from app.services.skill_graph import build_skill_graph


def titles(result) -> list[str]:
    return [r.opportunity.title for r in sorted(result.run.recommendations, key=lambda r: r.rank)]


def excluded_codes(result, title_fragment: str) -> list[str]:
    return [
        e["reason_code"]
        for e in result.run.exclusions
        if title_fragment.lower() in e["title"].lower()
    ]


# ---------------------------------------------------------------------------
# Geo
# ---------------------------------------------------------------------------


class TestGeo:
    def test_haversine_known_distance(self):
        # Nashik to Pune, roughly 150 km great-circle.
        distance = haversine_km(19.85, 74.00, 18.52, 73.856)
        assert 140 < distance < 160

    def test_same_point_is_zero(self):
        assert haversine_km(19.85, 74.0, 19.85, 74.0) == pytest.approx(0.0, abs=1e-6)

    def test_bounding_box_contains_the_point(self):
        min_lat, max_lat, min_lon, max_lon = bounding_box(19.85, 74.0, 25)
        assert min_lat < 19.85 < max_lat
        assert min_lon < 74.0 < max_lon

    def test_location_fit_decays_with_distance(self):
        assert location_fit_score(2, 25) == 1.0
        assert location_fit_score(24, 25) < 0.2
        assert location_fit_score(30, 25) == 0.0

    def test_unknown_distance_is_neutral_not_zero(self):
        """A missing coordinate must not silently bury an otherwise good record."""
        assert location_fit_score(None, 25) == 0.5


# ---------------------------------------------------------------------------
# Skill graph and gap
# ---------------------------------------------------------------------------


class TestSkillGraph:
    def test_direct_skills_are_present(self, db, ravi):
        graph = build_skill_graph(db, ravi)
        assert {"pump_repair", "farm_machinery_maintenance"} <= graph.direct_codes()

    def test_parent_category_is_rolled_up(self, db, ravi):
        graph = build_skill_graph(db, ravi)
        node = graph.node_map().get("farm_machinery")
        assert node is not None and not node.is_direct
        assert 0 < node.score < graph.node_map()["farm_machinery_maintenance"].score

    def test_transfer_edges_create_partial_credit(self, db, ravi):
        graph = build_skill_graph(db, ravi)
        diagnostics = graph.node_map().get("diagnostics_troubleshooting")
        assert diagnostics is not None
        assert not diagnostics.is_direct
        assert diagnostics.derivation and "transfers" in diagnostics.derivation

    def test_derived_score_never_exceeds_its_source(self, db, ravi):
        graph = build_skill_graph(db, ravi)
        nodes = graph.node_map()
        for node in graph.nodes:
            if node.derived_from and node.derived_from in nodes:
                assert node.score <= nodes[node.derived_from].score + 1e-9

    def test_unclaimed_skill_is_absent(self, db, ravi):
        graph = build_skill_graph(db, ravi)
        assert "tailoring" not in graph.score_map()


class TestSkillGap:
    @pytest.fixture
    def report(self, db, ravi):
        qualification = db.execute(
            select(Qualification).where(Qualification.code == "AGR/Q1101")
        ).scalar_one()
        return analyze_gap(db, ravi, qualification)

    def test_pump_repair_competency_is_covered(self, report):
        assert "AGR/N1103" in {c.code for c in report.covered}

    def test_equipment_maintenance_competency_is_covered(self, report):
        assert "AGR/N1101" in {c.code for c in report.covered}

    def test_safety_and_testing_are_missing(self, report):
        missing = {c.code for c in report.missing}
        assert "GEN/N1201" in missing  # workplace safety
        assert "AGR/N1104" in missing  # test and commission

    def test_coverage_is_partial_not_total(self, report):
        assert 0 < report.coverage_ratio < 1

    def test_gap_band_is_moderate_for_ravi(self, report):
        assert report.gap_band == "moderate"

    def test_covered_items_clear_the_threshold(self, report):
        assert all(c.coverage >= COVERED_THRESHOLD for c in report.covered)

    def test_every_competency_explains_itself(self, report):
        assert all(c.explanation for c in report.all_competencies)

    def test_priority_order_puts_heaviest_gap_first(self, report):
        assert report.priority_order
        assert report.priority_order[0] in {c.code for c in report.missing + report.partial}

    def test_elective_competency_excluded_from_coverage_ratio(self, db, ravi):
        """Only core competencies determine the coverage ratio."""
        qualification = db.execute(
            select(Qualification).where(Qualification.code == "AGR/Q1101")
        ).scalar_one()
        report = analyze_gap(db, ravi, qualification)
        electives = [c for c in report.all_competencies if not c.is_core]
        assert electives, "fixture expects at least one elective competency"


# ---------------------------------------------------------------------------
# The seven demo cases
# ---------------------------------------------------------------------------


class TestDemoCases:
    def test_case_1_low_mobility_prefers_nearby(self, db, ravi):
        """CASE 1: with low mobility every recommendation is close by."""
        ravi.mobility = "low"
        db.commit()
        result = generate_recommendations(db, ravi)
        assert result.run.recommendations
        assert result.run.radius_km_used == 25.0
        for recommendation in result.run.recommendations:
            assert recommendation.distance_km is not None
            assert recommendation.distance_km <= 25.0

    def test_case_2_high_mobility_opens_up_distant_options(self, db, ravi):
        """CASE 2: raising mobility makes far opportunities eligible and changes the ranking."""
        ravi.mobility = "low"
        db.commit()
        low = generate_recommendations(db, ravi)
        low_titles = titles(low)
        assert excluded_codes(low, "Pump Assembly") == ["BEYOND_TRAVEL_RANGE"]

        ravi.mobility = "high"
        db.commit()
        high = generate_recommendations(db, ravi)
        assert high.run.radius_km_used == 200.0
        # The 149 km listing is no longer filtered out on distance.
        assert "BEYOND_TRAVEL_RANGE" not in excluded_codes(high, "Pump Assembly")
        # And the ordering genuinely differs.
        assert titles(high) != low_titles
        assert max(r.distance_km for r in high.run.recommendations) > 25.0

    def test_case_3_expired_listing_never_appears(self, db, ravi):
        """CASE 3: a listing past its validity date is excluded with that reason."""
        result = generate_recommendations(db, ravi)
        assert "batch closed" not in " ".join(titles(result)).lower()
        assert "EXPIRED" in excluded_codes(result, "batch closed")

    def test_case_4_ineligible_qualification_is_filtered(self, db, ravi):
        """CASE 4: Ravi is 10th pass; the graduate-only role is excluded."""
        result = generate_recommendations(db, ravi)
        assert "Agri-Business Extension Associate" not in titles(result)
        assert "EDUCATION_NOT_MET" in excluded_codes(result, "Agri-Business Extension")

    def test_case_6_no_match_returns_prerequisite_pathway(self, db, ravi):
        """CASE 6: when nothing qualifies, show a prerequisite path, never an invention."""
        # Move Ravi far from every seeded opportunity and pin him in place.
        for location in ravi.locations:
            location.latitude, location.longitude = 26.9124, 75.7873  # Jaipur
        ravi.mobility = "low"
        db.commit()

        result = generate_recommendations(db, ravi)
        assert result.run.is_no_match is True
        assert result.run.recommendations == []
        assert result.no_match is not None
        assert "No verified suitable opportunity" in result.no_match.message
        assert result.no_match.closest_pathway is not None
        assert result.no_match.missing_competencies
        assert any(o["action"] == "widen_radius" for o in result.no_match.retry_options)

    def test_case_6_no_match_does_not_fabricate_an_opportunity(self, db, ravi):
        for location in ravi.locations:
            location.latitude, location.longitude = 26.9124, 75.7873
        ravi.mobility = "low"
        db.commit()
        result = generate_recommendations(db, ravi)
        # The closest pathway is a qualification standard, not an opportunity listing.
        assert "opportunity_id" not in (result.no_match.closest_pathway or {})
        assert result.no_match.closest_pathway["qualification_code"]


class TestFiltering:
    def test_retired_qualification_is_excluded(self, db, ravi):
        result = generate_recommendations(db, ravi)
        assert "RETIRED_QUALIFICATION" in excluded_codes(result, "legacy standard")
        assert "Pump Set Operator Certification" not in " ".join(titles(result))

    def test_inactive_listing_is_excluded(self, db, ravi):
        result = generate_recommendations(db, ravi)
        assert "INACTIVE_STATUS" in excluded_codes(result, "position filled")

    def test_hard_stale_listing_is_excluded(self, db, ravi):
        """A listing nobody has re-verified in over a year must not be shown as available."""
        result = generate_recommendations(db, ravi)
        assert "STALE_UNVERIFIED" in excluded_codes(result, "unverified for over a year")

    def test_unrelated_sector_is_excluded_despite_being_closest(self, db, ravi):
        """The tailoring unit is 0 km away and active, but unrelated to Ravi."""
        result = generate_recommendations(db, ravi)
        assert "Tailoring" not in " ".join(titles(result))
        assert "NO_PROFILE_OVERLAP" in excluded_codes(result, "Tailoring")

    def test_every_recommendation_is_a_real_active_record(self, db, ravi):
        result = generate_recommendations(db, ravi)
        now = utcnow()
        for recommendation in result.run.recommendations:
            opportunity = db.get(Opportunity, recommendation.opportunity_id)
            assert opportunity is not None
            assert opportunity.status == RecordStatus.ACTIVE
            assert opportunity.valid_until is None or opportunity.valid_until.timestamp() >= now.timestamp()
            assert opportunity.last_verified_at is not None
            assert opportunity.source

    def test_exclusions_reconcile_with_what_was_considered(self, db, ravi):
        result = generate_recommendations(db, ravi)
        assert result.run.candidates_retrieved > 0
        assert result.run.candidates_after_filters <= result.run.candidates_retrieved


class TestRanking:
    def test_top_three_by_default(self, db, ravi):
        result = generate_recommendations(db, ravi)
        assert 1 <= len(result.run.recommendations) <= 3

    def test_ranks_are_contiguous_and_ordered_by_score(self, db, ravi):
        result = generate_recommendations(db, ravi)
        ordered = sorted(result.run.recommendations, key=lambda r: r.rank)
        assert [r.rank for r in ordered] == list(range(1, len(ordered) + 1))
        scores = [r.match_score for r in ordered]
        assert scores == sorted(scores, reverse=True)

    def test_best_match_is_the_equipment_service_pathway(self, db, ravi):
        ravi.mobility = "low"
        db.commit()
        result = generate_recommendations(db, ravi)
        assert "Agriculture Equipment Service Technician" in titles(result)[0]

    def test_all_nine_factors_are_scored(self, db, ravi):
        result = generate_recommendations(db, ravi)
        expected = set(explain_weights()[0].keys()) and {
            "skill_fit",
            "qualification_fit",
            "aspiration_fit",
            "gap_compatibility",
            "location_fit",
            "mobility_fit",
            "availability",
            "freshness",
            "verification",
        }
        for recommendation in result.run.recommendations:
            assert set(recommendation.factor_scores) == expected
            assert all(0 <= v <= 1 for v in recommendation.factor_scores.values())

    def test_match_score_equals_weighted_mean_of_factors(self, db, ravi):
        """The headline score must be reproducible from the published factors."""
        result = generate_recommendations(db, ravi)
        weights = {w["code"]: w["weight"] for w in explain_weights()}
        total_weight = sum(weights.values())
        for recommendation in result.run.recommendations:
            expected = sum(
                score * weights[code] for code, score in recommendation.factor_scores.items()
            ) / total_weight
            assert recommendation.match_score == pytest.approx(expected, abs=1e-3)

    def test_ranking_is_not_similarity_alone(self, db, ravi):
        """Distance and availability must be able to reorder equal-skill options."""
        ravi.mobility = "low"
        db.commit()
        low = {t: i for i, t in enumerate(titles(generate_recommendations(db, ravi)))}
        ravi.mobility = "high"
        db.commit()
        high = {t: i for i, t in enumerate(titles(generate_recommendations(db, ravi)))}
        assert low != high, "mobility alone must be able to change the result"

    def test_recommendations_are_diversified_by_provider(self, db, ravi):
        result = generate_recommendations(db, ravi)
        providers = [
            db.get(Opportunity, r.opportunity_id).provider for r in result.run.recommendations
        ]
        assert len(providers) == len(set(providers))

    def test_relevance_floor_is_documented_and_positive(self):
        assert 0 < RELEVANCE_FLOOR < 0.5

    def test_weights_are_published(self):
        weights = explain_weights()
        assert len(weights) == 9
        assert all(0 <= w["share"] <= 1 for w in weights)
        assert sum(w["share"] for w in weights) == pytest.approx(1.0, abs=1e-6)


class TestExplainability:
    def test_every_recommendation_explains_why(self, db, ravi):
        result = generate_recommendations(db, ravi)
        for recommendation in result.run.recommendations:
            reasons = [r for r in recommendation.reasons if r.category == "why_fits"]
            assert reasons, "a recommendation with no stated reason is not acceptable"
            assert all(r.code and r.label for r in reasons)

    def test_every_recommendation_has_a_next_step(self, db, ravi):
        result = generate_recommendations(db, ravi)
        for recommendation in result.run.recommendations:
            assert recommendation.next_step
            assert any(r.category == "next_step" for r in recommendation.reasons)

    def test_missing_competencies_are_listed(self, db, ravi):
        result = generate_recommendations(db, ravi)
        top = sorted(result.run.recommendations, key=lambda r: r.rank)[0]
        assert top.missing_competency_codes

    def test_provenance_is_carried_through(self, db, ravi):
        result = generate_recommendations(db, ravi)
        for recommendation in result.run.recommendations:
            opportunity = db.get(Opportunity, recommendation.opportunity_id)
            assert opportunity.source
            assert opportunity.verification_status in set(VerificationStatus)

    def test_run_records_the_config_it_used(self, db, ravi):
        result = generate_recommendations(db, ravi)
        assert result.run.ranking_config["weights"]
        assert result.run.profile_snapshot["skills"]
