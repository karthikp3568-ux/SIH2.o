# API reference

Base path `/api`. Interactive docs at `/docs` (Swagger) and `/redoc`.
Authentication is `Authorization: Bearer <access_token>`.

---

## System and transparency

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/system/health` | — | Liveness plus a database round-trip |
| GET | `/system/status` | — | Every provider's real configured state, and capabilities |
| GET | `/system/languages` | — | Supported languages with their BCP-47 speech tags |
| GET | `/system/slots?language=` | — | Conversation slot configuration (the client renders this) |
| GET | `/system/ranking-config` | — | Published weights, radii and the caveat |
| GET | `/system/reason-codes` | — | Stable exclusion and rejection codes |

`/system/status` is the honesty endpoint: it reports which integrations are
live and which are interface-only.

---

## Authentication

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | — | Creates a **beneficiary**. Requires `consent_profile_processing`. A `role` field in the body is ignored. |
| POST | `/auth/login` | — | Rate limited; identical error for unknown email and wrong password |
| POST | `/auth/refresh` | — | Exchanges a refresh token |
| POST | `/auth/logout` | user | Bumps `token_version`, revoking every issued token |
| GET | `/auth/me` | user | Current account |
| GET | `/auth/consents` | user | Purpose-scoped consent records |
| PUT | `/auth/consents` | user | Grant or withdraw one purpose |
| DELETE | `/auth/me` | user | Erases the account and all cascading data |

```jsonc
// POST /auth/register
{
  "email": "person@example.com",
  "full_name": "Name",
  "password": "Str0ngPass1",
  "preferred_language": "hi",
  "consent_profile_processing": true,     // required
  "consent_voice_processing": true,
  "consent_location_processing": true,
  "consent_outcome_tracking": false
}
```

---

## Phase 1 — Conversation

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/conversation/start` | beneficiary | Start or resume; returns greeting, slots, speech tag |
| POST | `/conversation/{id}/message` | beneficiary | One turn |
| GET | `/conversation/{id}` | beneficiary | Full transcript and draft |
| POST | `/conversation/{id}/confirm` | beneficiary | **The only path from draft to profile** |
| POST | `/speech/transcribe` | user | Server-side ASR when configured; 503 with an explanation otherwise |
| GET | `/channels/status` | — | What each channel can receive and send |
| POST | `/channels/{whatsapp\|ivr}/inbound` | — | Normalise a webhook payload |

```jsonc
// POST /conversation/{id}/message
{
  "text": "I work in agriculture and I repair pumps sometimes",
  "language": "en",
  "asr_confidence": 0.91,          // omit for typed input
  "speech_provider": "browser_web_speech",
  "slot_answer": "low"             // when a choice was tapped
}
```

```jsonc
// response
{
  "assistant_message": "Got it. How far did you study?",
  "pending_slot": { "name": "education", "question": "...", "options": [...] },
  "draft_profile": { "skills": [...], "mobility": {...} },
  "extraction": { "language": "en", "language_confidence": 0.93, "skills": [...] },
  "newly_filled": ["skills", "mobility", "goal"],
  "needs_confirmation": false,     // true when ASR confidence was too low
  "transcript_for_correction": null,
  "ready_to_confirm": false,
  "progress": { "percent": 66, "required": [...], "required_filled": [...] }
}
```

When `needs_confirmation` is `true`, **nothing was committed to the draft** —
show `transcript_for_correction` and let the user accept or edit it.

---

## Phase 2 — Profile, skills, gap

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/beneficiary/profile` | beneficiary | Own profile |
| GET | `/beneficiary/{id}/profile` | owner or staff | Non-owners get 404, not 403 |
| PATCH | `/beneficiary/profile` | beneficiary | Corrections (verification status is not editable here) |
| PUT | `/beneficiary/location` | beneficiary | GPS, PIN code or manual, with provenance |
| POST | `/beneficiary/skills` | beneficiary | Add a skill — recorded as self-declared |
| DELETE | `/beneficiary/skills/{id}` | beneficiary | Remove |
| POST | `/profile/extract` | user | Extract from text, committing nothing |
| POST | `/skills/normalize` | user | Free-text labels → taxonomy codes |
| GET | `/skills/taxonomy` | — | The canonical taxonomy |
| GET | `/skills/{beneficiary_id}` | owner or staff | Skills plus derived graph |
| GET | `/skill-graph/{beneficiary_id}` | owner or staff | Graph only |
| POST | `/skill-gap/analyze` | beneficiary | Coverage against one or more qualifications |

```jsonc
// POST /skill-gap/analyze  →  reports[0]
{
  "qualification_code": "AGR/Q1101",
  "qualification_title": "Agriculture Equipment Service Technician",
  "nsqf_level": 4,
  "coverage_ratio": 0.42,
  "gap_band": "moderate",
  "covered": [ { "code": "AGR/N1103", "name": "Repair pumps and irrigation equipment",
                 "coverage": 0.75, "explanation": "Largely covered by your pump repair." } ],
  "partial": [ ... ],
  "missing": [ { "code": "GEN/N1201", "name": "Maintain workplace health and safety", ... } ],
  "priority_order": ["GEN/N1201", "AGR/N1104", ...]
}
```

---

## Catalogue

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/qualifications/search` | — | Retired standards excluded unless `include_retired=true` |
| GET | `/qualifications/by-code/{code}` | — | Use this for QP codes containing a slash |
| GET | `/qualifications/{id}` | — | By UUID |
| GET | `/competencies/search` | — | Competency lookup |
| GET | `/opportunities/search` | user | Unranked browsing, with distances |
| GET | `/training/search` | user | Training and apprenticeships only |
| GET | `/opportunities/{id}` | — | One listing, with an availability note |

Search deliberately does **not** rank or personalise. Keeping it separate from
`/recommendations` means the raw data behind any recommendation is inspectable.

---

## Phase 3 — Recommendations

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/recommendations/generate` | beneficiary | Run the pipeline |
| GET | `/recommendations/{beneficiary_id}` | owner or staff | Latest run |
| GET | `/recommendations/{beneficiary_id}/history` | owner or staff | How advice changed over time |
| GET | `/recommendations/{beneficiary_id}/exclusions` | owner or staff | Grouped "why not" |
| GET | `/recommendations/detail/{id}/explanation` | owner or staff | Factors, reasons, gap, provenance |
| GET | `/pathways/preview` | beneficiary | Qualification-level standing, independent of listings |
| POST | `/pathways/{pathway_id}/select` | beneficiary | Choose one |

```jsonc
// POST /recommendations/generate
{
  "mobility": "high",        // what-if only; does NOT rewrite the stored profile
  "radius_km": 150,
  "top_n": 3,
  "search_wider": false      // explicit user-initiated relaxation, never silent
}
```

```jsonc
// response
{
  "run_id": "…",
  "mobility_used": "high",
  "radius_km_used": 200.0,
  "candidates_considered": 18,
  "candidates_after_filters": 9,
  "is_no_match": false,
  "recommendations": [
    {
      "id": "…",
      "pathway_id": "…",                  // pass this to /pathways/{id}/select
      "rank": 1,
      "title": "Agriculture Equipment Service Technician - Skill Training Batch",
      "provider": "Nashik District Agri Skill Centre, Sinnar",
      "match_score": 0.8,
      "skill_fit": "good",
      "eligibility": "eligible",
      "distance_km": 11.94,
      "mobility_fit": "high",
      "availability": "active",
      "skill_gap": "moderate",
      "skill_gaps": ["Test and commission repaired equipment", "..."],
      "skills_you_have": [{ "code": "pump_repair", "name": "Pump repair" }],
      "why_it_fits": ["Skill overlap", "Eligibility and level", "..."],
      "cautions": [],
      "next_step": "Contact … to confirm the next batch date and the fee, then enrol.",
      "source": "District Skill Development Centre listing (prototype seed data)",
      "verification_status": "admin_verified",
      "last_verified_at": "2026-09-24T…",
      "qualification": { "code": "AGR/Q1101", "nsqf_level": 4, "status": "active" }
    }
  ],
  "exclusions": [
    { "title": "…", "reason_code": "EXPIRED", "reason": "…", "detail": "valid until 2026-09-18" }
  ],
  "ranking_weights": [ { "code": "skill_fit", "label": "…", "weight": 0.26, "share": 0.26 } ]
}
```

### No-match response

```jsonc
{
  "is_no_match": true,
  "recommendations": [],
  "no_match": {
    "message": "No verified suitable opportunity was found: every nearby listing is further than the distance you said you can travel.",
    "closest_pathway": { "qualification_code": "AGR/Q1101", "coverage_ratio": 0.42, "source": "…" },
    "missing_competencies": [ … ],
    "prerequisite_suggestions": [ … ],
    "what_to_verify": [ … ],
    "retry_options": [ { "action": "widen_radius", "label": "Search a wider area", "detail": "…" } ]
  }
}
```

### Exclusion reason codes

`INACTIVE_STATUS` · `EXPIRED` · `NOT_YET_OPEN` · `STALE_UNVERIFIED` ·
`NO_SEATS` · `RETIRED_QUALIFICATION` · `EDUCATION_NOT_MET` ·
`AGE_OUT_OF_RANGE` · `BEYOND_TRAVEL_RANGE` · `NO_PROFILE_OVERLAP`

---

## Phase 4 — Outcomes and feedback

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/outcomes` | beneficiary | Select a pathway by recommendation id |
| GET | `/outcomes` | beneficiary | Own outcomes |
| GET | `/outcomes/beneficiary/{id}` | owner or staff | For one beneficiary |
| PATCH | `/outcomes/{id}` | owner or staff | Advance the lifecycle; 409 names allowed steps |
| POST | `/feedback` | beneficiary | Subjective feedback |
| GET | `/feedback/reasons` | — | Structured rejection reasons |

Valid transitions are enforced server side:

```
recommended → selected | rejected | opportunity_inactive
selected    → enrolled | rejected | changed_pathway | opportunity_inactive
enrolled    → attending | dropped_out | changed_pathway | opportunity_inactive
attending   → completed | dropped_out | changed_pathway
completed   → employed | self_employed | changed_pathway
```

---

## Admin and counsellor

`staff` = admin or counsellor. `admin` = admin only.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/opportunities` | staff | List; `needs_review=true` for the review queue |
| POST | `/admin/opportunities` | admin | Create — always **draft** and **unverified** |
| PATCH | `/admin/opportunities/{id}` | admin | Update; changed fields are audited |
| DELETE | `/admin/opportunities/{id}` | admin | Soft deactivate (outcomes reference these rows) |
| POST | `/admin/opportunities/{id}/verify` | staff | Record a human check; may extend validity |
| POST | `/admin/opportunities/import` | admin | CSV; `dry_run=true` by default |
| POST | `/admin/knowledge/reindex` | admin | Rebuild the RAG index |
| GET | `/admin/beneficiaries` | staff | Directory |
| GET | `/admin/beneficiaries/{id}/extraction` | staff | Turn-by-turn AI extraction review |
| PATCH | `/admin/beneficiaries/{id}/profile` | staff | Correct a profile |
| POST | `/admin/recommendations/{id}/override` | staff | `accept` / `edit` / `reject`, note required |
| GET | `/admin/analytics` | staff | Dashboard; flags demo data |
| GET | `/admin/audit` | staff | Audit log, filterable |
| GET | `/admin/users` | admin | Accounts |
| POST | `/admin/users` | admin | **The only route that can assign a privileged role** |
| POST | `/admin/users/{id}/deactivate` | admin | Disable and revoke live tokens |

A rejected recommendation cannot subsequently be selected by the beneficiary —
`/pathways/{id}/select` returns 409.

---

## Demo (only when `DEMO_MODE=true`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/demo/script` | The scripted utterances |
| POST | `/demo/ravi/reset` | Reset Ravi and return a **beneficiary** session |
| GET | `/demo/status` | Seed counts and the honest-limitations list |

All three return 404 when demo mode is off, and refuse under
`ENVIRONMENT=production`. The reset route can only ever issue a session for one
fixed, non-privileged account.

---

## Errors

```jsonc
// 422
{
  "detail": "Some of the information provided was not valid.",
  "problems": [{ "field": "password", "message": "Value error, Password must contain a digit" }]
}
```

| Status | Meaning |
|---|---|
| 401 | Missing, invalid, expired or revoked token |
| 403 | Authenticated but lacking the role |
| 404 | Not found — or found but not yours (ids are not confirmed) |
| 409 | Conflict: duplicate email, invalid lifecycle transition, rejected pathway |
| 413 | Audio upload over `MAX_AUDIO_BYTES` |
| 422 | Validation failure, with per-field problems |
| 429 | Rate limited; `Retry-After` header is set |
| 503 | Database or a required provider unavailable |
