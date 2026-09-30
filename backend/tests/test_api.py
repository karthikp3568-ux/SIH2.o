"""End-to-end API tests: auth, RBAC, conversation, outcomes and admin control."""

from __future__ import annotations

import pytest

from conftest import auth


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class TestSystem:
    def test_health(self, client):
        response = client.get("/api/system/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_provider_status_declares_what_is_live(self, client):
        body = client.get("/api/system/status").json()
        assert "providers" in body
        speech = {p["name"]: p for p in body["providers"]["speech"]}
        # BHASHINI must report itself as not configured rather than pretending.
        assert speech["bhashini"]["configured"] is False
        assert "not configured" in speech["bhashini"]["detail"].lower()

    def test_ranking_config_is_public_and_carries_the_caveat(self, client):
        body = client.get("/api/system/ranking-config").json()
        assert len(body["weights"]) == 9
        assert "not empirically validated" in body["note"]

    def test_slots_are_served_from_the_backend(self, client):
        slots = client.get("/api/system/slots", params={"language": "hi"}).json()
        names = {s["name"] for s in slots}
        assert {"occupation", "skills", "education", "goal", "mobility", "location"} <= names
        mobility = next(s for s in slots if s["name"] == "mobility")
        assert mobility["options"] and all(o["label"] for o in mobility["options"])

    def test_languages_include_speech_tags(self, client):
        languages = client.get("/api/system/languages").json()
        assert any(lang["code"] == "hi" and lang["speech_tag"] == "hi-IN" for lang in languages)


# ---------------------------------------------------------------------------
# Auth and RBAC
# ---------------------------------------------------------------------------


class TestAuth:
    def test_register_requires_consent(self, client):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "noconsent@example.com",
                "full_name": "No Consent",
                "password": "Str0ngPass1",
                "consent_profile_processing": False,
            },
        )
        assert response.status_code == 422

    def test_register_rejects_weak_password(self, client):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "weak@example.com",
                "full_name": "Weak Password",
                "password": "password",
                "consent_profile_processing": True,
            },
        )
        assert response.status_code == 422

    def test_register_creates_a_beneficiary_not_an_admin(self, client):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "full_name": "New User",
                "password": "Str0ngPass1",
                "consent_profile_processing": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["user"]["role"] == "beneficiary"

    def test_role_cannot_be_self_assigned(self, client):
        """Sending role=admin must not escalate - the field is ignored entirely."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "sneaky@example.com",
                "full_name": "Sneaky",
                "password": "Str0ngPass1",
                "consent_profile_processing": True,
                "role": "admin",
            },
        )
        assert response.status_code == 201
        assert response.json()["user"]["role"] == "beneficiary"

    def test_login_failure_does_not_reveal_whether_the_email_exists(self, client):
        unknown = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "Whatever1"}
        )
        known = client.post(
            "/api/auth/login",
            json={"email": "ravi@navigator.example.com", "password": "WrongPassword1"},
        )
        assert unknown.status_code == known.status_code == 401
        assert unknown.json()["detail"] == known.json()["detail"]

    def test_unauthenticated_request_is_rejected(self, client):
        assert client.get("/api/beneficiary/profile").status_code == 401

    def test_garbage_token_is_rejected(self, client):
        response = client.get("/api/beneficiary/profile", headers=auth("not-a-real-token"))
        assert response.status_code == 401


class TestRBAC:
    def test_beneficiary_cannot_reach_admin_endpoints(self, client, beneficiary_token):
        assert client.get("/api/admin/opportunities", headers=auth(beneficiary_token)).status_code == 403
        assert client.get("/api/admin/analytics", headers=auth(beneficiary_token)).status_code == 403
        assert client.get("/api/admin/audit", headers=auth(beneficiary_token)).status_code == 403

    def test_beneficiary_cannot_create_users(self, client, beneficiary_token):
        response = client.post(
            "/api/admin/users",
            headers=auth(beneficiary_token),
            json={
                "email": "escalate@example.com",
                "full_name": "Escalate",
                "password": "Str0ngPass1",
                "role": "admin",
            },
        )
        assert response.status_code == 403

    def test_admin_can_reach_admin_endpoints(self, client, admin_token):
        assert client.get("/api/admin/analytics", headers=auth(admin_token)).status_code == 200

    def test_beneficiary_cannot_read_another_profile(self, client, beneficiary_token, db):
        from app.models import BeneficiaryProfile
        from sqlalchemy import select

        other = client.post(
            "/api/auth/register",
            json={
                "email": "other-person@example.com",
                "full_name": "Other Person",
                "password": "Str0ngPass1",
                "consent_profile_processing": True,
            },
        ).json()
        profile_id = db.execute(
            select(BeneficiaryProfile.id).where(
                BeneficiaryProfile.user_id == other["user"]["id"]
            )
        ).scalar_one()
        response = client.get(
            f"/api/beneficiary/{profile_id}/profile", headers=auth(beneficiary_token)
        )
        # 404 rather than 403: we do not confirm that the id exists.
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class TestConversation:
    @pytest.fixture
    def conversation_id(self, client, beneficiary_token):
        response = client.post(
            "/api/conversation/start",
            headers=auth(beneficiary_token),
            json={"language": "en", "channel": "web_text", "resume": False},
        )
        assert response.status_code == 200, response.text
        return response.json()["conversation"]["id"]

    def test_start_returns_a_greeting_and_the_slot_catalogue(self, client, beneficiary_token):
        body = client.post(
            "/api/conversation/start",
            headers=auth(beneficiary_token),
            json={"language": "en", "resume": False},
        ).json()
        assert body["assistant_message"]
        assert body["slots"]
        assert body["speech_language_tag"] == "en-IN"

    def test_message_extracts_and_asks_the_next_question(
        self, client, beneficiary_token, conversation_id
    ):
        body = client.post(
            f"/api/conversation/{conversation_id}/message",
            headers=auth(beneficiary_token),
            json={
                "text": (
                    "I work in agriculture and I repair pumps sometimes. I want to earn more. "
                    "I like mechanical work but I cannot travel very far."
                )
            },
        ).json()
        codes = {s["code"] for s in body["extraction"]["skills"]}
        assert "pump_repair" in codes
        assert body["draft_profile"]["mobility"]["value"] == "low"
        assert body["pending_slot"] is not None
        assert body["assistant_message"]

    def test_case_5_low_asr_confidence_asks_for_confirmation(
        self, client, beneficiary_token, conversation_id
    ):
        """CASE 5: a poor transcription must be confirmed, never silently committed."""
        body = client.post(
            f"/api/conversation/{conversation_id}/message",
            headers=auth(beneficiary_token),
            json={"text": "I repair pumps", "asr_confidence": 0.31, "speech_provider": "mock"},
        ).json()
        assert body["needs_confirmation"] is True
        assert body["transcript_for_correction"] == "I repair pumps"
        # Nothing was written into the draft from the doubtful turn.
        assert body["draft_profile"]["skills"] == []

    def test_high_asr_confidence_is_accepted(
        self, client, beneficiary_token, conversation_id
    ):
        body = client.post(
            f"/api/conversation/{conversation_id}/message",
            headers=auth(beneficiary_token),
            json={"text": "I repair pumps", "asr_confidence": 0.92, "speech_provider": "mock"},
        ).json()
        assert body["needs_confirmation"] is False
        assert {s["code"] for s in body["draft_profile"]["skills"]} == {"pump_repair"}

    def test_conversation_is_resumable(self, client, beneficiary_token, conversation_id):
        client.post(
            f"/api/conversation/{conversation_id}/message",
            headers=auth(beneficiary_token),
            json={"text": "I repair pumps and farm machinery"},
        )
        resumed = client.post(
            "/api/conversation/start",
            headers=auth(beneficiary_token),
            json={"resume": True},
        ).json()
        assert resumed["conversation"]["id"] == conversation_id
        assert resumed["conversation"]["draft_profile"]["skills"]

    def test_profile_is_not_written_until_confirmation(
        self, client, beneficiary_token, conversation_id
    ):
        client.post(
            f"/api/conversation/{conversation_id}/message",
            headers=auth(beneficiary_token),
            json={"text": "I repair pumps and farm machinery for 5 years, I am 10th pass"},
        )
        profile = client.get(
            "/api/beneficiary/profile", headers=auth(beneficiary_token)
        ).json()
        assert profile["is_confirmed"] is False

    def test_confirm_writes_the_profile(self, client, beneficiary_token, conversation_id):
        client.post(
            f"/api/conversation/{conversation_id}/message",
            headers=auth(beneficiary_token),
            json={
                "text": (
                    "I work in agriculture and repair pumps and farm machinery for 5 years. "
                    "I am 10th pass. I want to start my own work. I cannot travel far."
                )
            },
        )
        body = client.post(
            f"/api/conversation/{conversation_id}/confirm",
            headers=auth(beneficiary_token),
            json={
                "generate_recommendations": True,
                "location": {
                    "village": "Wadgaon",
                    "district": "Nashik",
                    "state": "Maharashtra",
                    "latitude": 19.85,
                    "longitude": 74.0,
                    "source": "manual",
                },
            },
        ).json()
        assert body["profile"]["is_confirmed"] is True
        assert {s["code"] for s in body["profile"]["skills"]} >= {"pump_repair"}
        assert body["recommendations_generated"] is True

    def test_extraction_endpoint_commits_nothing(self, client, beneficiary_token):
        before = client.get("/api/beneficiary/profile", headers=auth(beneficiary_token)).json()
        client.post(
            "/api/profile/extract",
            headers=auth(beneficiary_token),
            json={"text": "I am a graduate welder with 10 years of experience"},
        )
        after = client.get("/api/beneficiary/profile", headers=auth(beneficiary_token)).json()
        assert before["skills"] == after["skills"]
        assert before["education"] == after["education"]


# ---------------------------------------------------------------------------
# Speech and channels
# ---------------------------------------------------------------------------


class TestSpeechAndChannels:
    def test_rejects_empty_audio(self, client, beneficiary_token):
        response = client.post(
            "/api/speech/transcribe",
            headers=auth(beneficiary_token),
            files={"audio": ("clip.webm", b"", "audio/webm")},
        )
        assert response.status_code == 400

    def test_mock_provider_transcribes(self, client, beneficiary_token):
        response = client.post(
            "/api/speech/transcribe",
            headers=auth(beneficiary_token),
            files={"audio": ("clip.webm", b"\x00\x01\x02", "audio/webm")},
            data={"language": "en"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "mock"
        assert body["stored_audio"] is False

    def test_whatsapp_inbound_payload_is_normalised(self, client):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"language": "hi"}],
                                "messages": [
                                    {
                                        "from": "919876543210",
                                        "id": "wamid.TEST",
                                        "type": "text",
                                        "text": {"body": "मैं पंप ठीक करता हूँ"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        body = client.post("/api/channels/whatsapp/inbound", json=payload).json()
        assert body["accepted"] is True
        assert body["sender_ref"] == "919876543210"
        assert body["text"] == "मैं पंप ठीक करता हूँ"
        # Sending is honestly reported as unavailable without credentials.
        assert body["outbound_sending_configured"] is False

    def test_malformed_channel_payload_is_rejected(self, client):
        assert client.post("/api/channels/whatsapp/inbound", json={"nope": 1}).status_code == 400

    def test_unknown_channel_404s(self, client):
        assert client.post("/api/channels/telex/inbound", json={}).status_code == 404


# ---------------------------------------------------------------------------
# Recommendations, outcomes, feedback
# ---------------------------------------------------------------------------


class TestRecommendationApi:
    @pytest.fixture
    def generated(self, client, beneficiary_token, ravi):
        response = client.post(
            "/api/recommendations/generate",
            headers=auth(beneficiary_token),
            json={"mobility": "low"},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_response_shape_matches_the_contract(self, generated):
        assert generated["recommendations"]
        first = generated["recommendations"][0]
        for field in (
            "pathway_id", "title", "match_score", "skill_fit", "eligibility",
            "distance_km", "mobility_fit", "availability", "skill_gaps",
            "why_it_fits", "next_step", "source", "last_verified_at",
        ):
            assert field in first, f"missing {field}"

    def test_scores_are_normalised(self, generated):
        assert all(0 <= r["match_score"] <= 1 for r in generated["recommendations"])

    def test_weights_are_returned_with_the_result(self, generated):
        assert len(generated["ranking_weights"]) == 9

    def test_exclusions_are_available_with_reasons(self, client, beneficiary_token, ravi, generated):
        body = client.get(
            f"/api/recommendations/{ravi.id}/exclusions", headers=auth(beneficiary_token)
        ).json()
        assert body["by_reason"]
        assert all(group["reason"] for group in body["by_reason"])

    def test_explanation_endpoint(self, client, beneficiary_token, generated):
        recommendation_id = generated["recommendations"][0]["id"]
        body = client.get(
            f"/api/recommendations/detail/{recommendation_id}/explanation",
            headers=auth(beneficiary_token),
        ).json()
        assert len(body["factors"]) == 9
        assert body["why_it_fits"]
        assert body["next_step"]
        assert body["evidence"]["source"]
        assert "weighted average" in body["method_note"]

    def test_explanation_exposes_no_internal_reasoning(self, client, beneficiary_token, generated):
        recommendation_id = generated["recommendations"][0]["id"]
        body = client.get(
            f"/api/recommendations/detail/{recommendation_id}/explanation",
            headers=auth(beneficiary_token),
        ).text.lower()
        for leaked in ("system prompt", "chain of thought", "you are an", "<thinking>"):
            assert leaked not in body

    def test_mobility_override_does_not_mutate_the_profile(
        self, client, beneficiary_token, ravi, db
    ):
        client.post(
            "/api/recommendations/generate",
            headers=auth(beneficiary_token),
            json={"mobility": "high"},
        )
        db.refresh(ravi)
        assert ravi.mobility == "low"


class TestOutcomeLifecycle:
    @pytest.fixture
    def outcome(self, client, beneficiary_token, ravi):
        generated = client.post(
            "/api/recommendations/generate",
            headers=auth(beneficiary_token),
            json={"mobility": "low"},
        ).json()
        pathway_id = generated["recommendations"][0]["pathway_id"]
        response = client.post(
            f"/api/pathways/{pathway_id}/select",
            headers=auth(beneficiary_token),
            json={"note": "I will try this one"},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_selection_creates_an_outcome(self, outcome):
        assert outcome["status"] == "selected"
        assert outcome["status_history"]
        assert "enrolled" in outcome["allowed_next"]

    def test_selecting_an_unrecommended_pathway_is_refused(self, client, beneficiary_token):
        response = client.post(
            "/api/pathways/00000000-0000-0000-0000-000000000000/select",
            headers=auth(beneficiary_token),
            json={},
        )
        assert response.status_code == 404

    def test_lifecycle_progresses(self, client, beneficiary_token, outcome):
        for step in ("enrolled", "attending", "completed", "self_employed"):
            response = client.patch(
                f"/api/outcomes/{outcome['id']}",
                headers=auth(beneficiary_token),
                json={"status": step, "note": f"moved to {step}"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == step
        final = response.json()
        assert final["outcome_type"] == "self_employed"
        assert len(final["status_history"]) >= 4

    def test_invalid_transition_is_refused_with_a_reason(
        self, client, beneficiary_token, outcome
    ):
        """`recommended` is never a valid target - the lifecycle does not run backwards."""
        response = client.patch(
            f"/api/outcomes/{outcome['id']}",
            headers=auth(beneficiary_token),
            json={"status": "recommended"},
        )
        assert response.status_code == 409
        assert "Allowed next steps" in response.json()["detail"]

    def test_feedback_is_recorded(self, client, beneficiary_token, outcome):
        response = client.post(
            "/api/feedback",
            headers=auth(beneficiary_token),
            json={
                "outcome_id": outcome["id"],
                "was_useful": True,
                "rating": 4,
                "comment": "The training centre was close to my village",
            },
        )
        assert response.status_code == 201

    def test_rejection_reason_must_be_a_known_code(self, client, beneficiary_token):
        response = client.post(
            "/api/feedback",
            headers=auth(beneficiary_token),
            json={"was_useful": False, "rejection_reason": "made_up_reason"},
        )
        assert response.status_code == 422

    def test_structured_rejection_reasons_are_published(self, client):
        reasons = client.get("/api/feedback/reasons").json()
        assert any(r["code"] == "too_far" for r in reasons)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class TestAdmin:
    def test_case_7_override_is_recorded_in_the_audit_log(
        self, client, admin_token, beneficiary_token, ravi
    ):
        """CASE 7: an admin override must be logged with actor, action and values."""
        generated = client.post(
            "/api/recommendations/generate",
            headers=auth(beneficiary_token),
            json={"mobility": "low"},
        ).json()
        recommendation_id = generated["recommendations"][0]["id"]

        response = client.post(
            f"/api/admin/recommendations/{recommendation_id}/override",
            headers=auth(admin_token),
            json={
                "action": "reject",
                "note": "Provider confirmed this batch is postponed",
            },
        )
        assert response.status_code == 200
        assert response.json()["is_overridden"] is True
        assert response.json()["override_action"] == "reject"

        log = client.get(
            "/api/admin/audit",
            headers=auth(admin_token),
            params={"action": "recommendation.override", "entity_id": recommendation_id},
        ).json()
        assert log, "override must appear in the audit log"
        entry = log[0]
        assert entry["actor_role"] == "admin"
        assert entry["new_value"]["override_action"] == "reject"
        assert entry["old_value"]["is_overridden"] is False

    def test_rejected_recommendation_cannot_be_selected(
        self, client, admin_token, beneficiary_token, ravi
    ):
        generated = client.post(
            "/api/recommendations/generate",
            headers=auth(beneficiary_token),
            json={"mobility": "low"},
        ).json()
        recommendation = generated["recommendations"][0]
        client.post(
            f"/api/admin/recommendations/{recommendation['id']}/override",
            headers=auth(admin_token),
            json={"action": "reject", "note": "Not suitable, batch postponed"},
        )
        response = client.post(
            f"/api/pathways/{recommendation['pathway_id']}/select",
            headers=auth(beneficiary_token),
            json={},
        )
        assert response.status_code == 409

    def test_override_requires_a_note(self, client, admin_token, beneficiary_token, ravi):
        generated = client.post(
            "/api/recommendations/generate",
            headers=auth(beneficiary_token),
            json={"mobility": "low"},
        ).json()
        response = client.post(
            f"/api/admin/recommendations/{generated['recommendations'][0]['id']}/override",
            headers=auth(admin_token),
            json={"action": "reject"},
        )
        assert response.status_code == 422

    def test_create_and_verify_an_opportunity_is_audited(self, client, admin_token):
        created = client.post(
            "/api/admin/opportunities",
            headers=auth(admin_token),
            json={
                "title": "Test Pump Technician Training",
                "provider": "Test Skill Centre",
                "opportunity_type": "training",
                "description": "A test training programme for pump repair technicians.",
                "source": "Test source for the automated test suite",
                "skills_required": ["pump repair"],
                "education_required": "class_10",
                "latitude": 19.9,
                "longitude": 74.0,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        # A newly created record is unverified and draft until a human checks it.
        assert body["verification_status"] == "unverified"
        assert body["status"] == "draft"
        assert body["skill_codes"] == ["pump_repair"]

        verified = client.post(
            f"/api/admin/opportunities/{body['id']}/verify",
            headers=auth(admin_token),
            json={"verification_status": "admin_verified", "note": "Checked with the centre"},
        ).json()
        assert verified["verification_status"] == "admin_verified"
        assert verified["last_verified_at"]

        log = client.get(
            "/api/admin/audit",
            headers=auth(admin_token),
            params={"entity_id": body["id"]},
        ).json()
        actions = {entry["action"] for entry in log}
        assert {"opportunity.created", "opportunity.verified"} <= actions

    def test_delete_is_a_soft_deactivate(self, client, admin_token):
        created = client.post(
            "/api/admin/opportunities",
            headers=auth(admin_token),
            json={
                "title": "Temporary Listing To Remove",
                "provider": "Test Provider",
                "opportunity_type": "job",
                "description": "A listing created purely to test deactivation behaviour.",
                "source": "Test source",
            },
        ).json()
        client.delete(f"/api/admin/opportunities/{created['id']}", headers=auth(admin_token))
        fetched = client.get(f"/api/opportunities/{created['id']}").json()
        assert fetched["status"] == "inactive"
        assert "not recommended" in fetched["availability_note"]

    def test_csv_import_dry_run_changes_nothing(self, client, admin_token):
        csv_body = (
            "external_id,title,provider,opportunity_type,description,source,latitude,longitude\n"
            "CSV-1,Imported Pump Course,CSV Centre,training,"
            "An imported training record for testing.,CSV test source,19.9,74.0\n"
        )
        before = client.get("/api/admin/opportunities", headers=auth(admin_token)).json()["total"]
        report = client.post(
            "/api/admin/opportunities/import",
            headers=auth(admin_token),
            files={"file": ("import.csv", csv_body, "text/csv")},
            params={"dry_run": True},
        ).json()
        assert report["dry_run"] is True
        assert report["created"] == 1
        after = client.get("/api/admin/opportunities", headers=auth(admin_token)).json()["total"]
        assert before == after

    def test_csv_import_reports_bad_rows_instead_of_dropping_them(self, client, admin_token):
        csv_body = (
            "external_id,title,provider,opportunity_type,description,source\n"
            "CSV-BAD,,Missing Title Provider,training,Description here,Some source\n"
        )
        report = client.post(
            "/api/admin/opportunities/import",
            headers=auth(admin_token),
            files={"file": ("import.csv", csv_body, "text/csv")},
            params={"dry_run": True},
        ).json()
        assert report["skipped"] == 1
        assert report["errors"][0]["errors"]

    def test_csv_missing_columns_is_rejected(self, client, admin_token):
        report = client.post(
            "/api/admin/opportunities/import",
            headers=auth(admin_token),
            files={"file": ("import.csv", "title,provider\nx,y\n", "text/csv")},
            params={"dry_run": True},
        )
        assert report.status_code == 422

    def test_analytics_never_presents_demo_figures_as_real(self, client, admin_token):
        """Whenever the data is still seed-only, the response must say so."""
        body = client.get("/api/admin/analytics", headers=auth(admin_token)).json()
        assert isinstance(body["is_demo_data"], bool)
        assert body["opportunities"]["total"] > 0
        if body["is_demo_data"]:
            assert "not real-world impact numbers" in body["disclaimer"]

    def test_seed_only_database_is_flagged_as_demo_data(self, db):
        from app.services import analytics

        assert analytics._looks_like_demo_data(db) in (True, False)
        assert analytics.overview(db)["beneficiaries"]["total"] >= 1

    def test_staff_can_review_ai_extraction(self, client, admin_token, ravi):
        body = client.get(
            f"/api/admin/beneficiaries/{ravi.id}/extraction", headers=auth(admin_token)
        ).json()
        assert body["profile"]["id"] == ravi.id
        assert "conversations" in body


class TestCatalogue:
    def test_retired_qualification_is_hidden_by_default(self, client):
        body = client.get("/api/qualifications/search", params={"q": "Pump Set Operator"}).json()
        assert body["total"] == 0

    def test_retired_qualification_can_be_inspected_with_a_warning(self, client):
        body = client.get("/api/qualifications/by-code/AGR/Q0901").json()
        assert body["status"] == "retired"
        assert "retired" in body["warning"]
        assert body["superseded_by_code"] == "AGR/Q1101"

    def test_qualification_detail_lists_competencies(self, client):
        body = client.get("/api/qualifications/by-code/AGR/Q1101").json()
        codes = {c["code"] for c in body["competencies"]}
        assert {"AGR/N1101", "AGR/N1103", "GEN/N1201"} <= codes
        assert body["nsqf_level"] == 4

    def test_opportunity_search_is_authenticated(self, client):
        assert client.get("/api/opportunities/search").status_code == 401

    def test_opportunity_search_returns_distances(self, client, beneficiary_token, ravi):
        body = client.get(
            "/api/opportunities/search",
            headers=auth(beneficiary_token),
            params={"q": "pump"},
        ).json()
        assert body["items"]
        assert body["distances_km"]


class TestDemoMode:
    def test_reset_returns_a_beneficiary_session_only(self, client):
        body = client.post("/api/demo/ravi/reset").json()
        assert body["user"]["role"] == "beneficiary"
        assert body["tokens"]["access_token"]
        assert body["conversation_id"]

    def test_demo_token_cannot_reach_admin(self, client):
        token = client.post("/api/demo/ravi/reset").json()["tokens"]["access_token"]
        assert client.get("/api/admin/analytics", headers=auth(token)).status_code == 403

    def test_status_declares_limitations(self, client):
        body = client.get("/api/demo/status").json()
        assert body["works_offline"] is True
        assert body["external_services_required"] == []
        assert any("not an authoritative extract" in line for line in body["honest_limitations"])
