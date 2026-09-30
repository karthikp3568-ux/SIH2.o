# AI-Driven Multilingual Livelihood Navigator

**Smart India Hackathon 2026 — Problem Statement SIH26097**
Theme: Agriculture, FoodTech & Rural Development · Category: Software

> Natural conversation → structured skill intelligence → recognised pathway →
> constrained opportunity matching → measured livelihood outcome.

A beneficiary speaks naturally in their own language about the work they do.
The system turns that into a structured profile, builds a skill graph, measures
the gap against NSQF-shaped qualification standards, retrieves **verified**
local opportunities, ranks them on nine explicit factors including distance and
mobility, explains every recommendation, and then tracks what actually happened.

The beneficiary remains the decision-maker throughout. The system suggests; it
never commits anyone to anything.

---

## Quick start

Two terminals, no Docker, no external service, no API key.

```bash
# 1. Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.cli seed
uvicorn app.main:app --reload --port 8000
```

```bash
# 2. Frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** and press **"Try Ravi Demo"**.

| Surface | URL |
|---|---|
| Beneficiary app | http://localhost:5173 |
| Admin console | http://localhost:5173/admin |
| What is really wired up | http://localhost:5173/system |
| API docs (Swagger) | http://localhost:8000/docs |

**Demo accounts** (seeded, exist only while `DEMO_MODE=true`):

| Role | Email | Password |
|---|---|---|
| Beneficiary | `ravi@navigator.example.com` | `Ravi@12345` |
| Administrator | `admin@navigator.example.com` | `Admin@12345` |
| Counsellor | `counsellor@navigator.example.com` | `Admin@12345` |

### See the whole journey in your terminal

```bash
cd backend
python -m app.cli demo
```

This runs Ravi's conversation, profile extraction, skill graph, skill gap and
ranking end to end and prints each stage — including the same ranking computed
at low and high mobility, so you can see the ordering change.

### Docker

```bash
docker compose up --build     # app on :8080, API on :8000
```

---

## What this actually is (and is not)

Hackathon projects are easy to overstate, so here is the honest inventory. The
running app reports the same thing at `/system`.

### Genuinely working, with no external dependency

- **Multilingual voice input** — Web Speech API in the browser (Chrome/Edge), real
  recognition in 11 Indian languages. Text input is an equal path everywhere.
- **Language identification and code-switch detection** — Unicode script analysis
  plus marker-word disambiguation (Hindi vs Marathi, romanised Indic in Latin script).
- **Profile extraction** — a deterministic multilingual lexicon plus taxonomy
  matching. Word order, plurals and gerunds are handled, so *"I repair pumps"*,
  *"pump repairing"* and *"पंप मरम्मत"* all reach the same node.
- **Skill graph** — parent roll-up and typed transfer edges, each derived score
  carrying the sentence that explains it.
- **Skill-gap engine** — per-competency coverage against qualification standards.
- **Hybrid retrieval** — local vector similarity + BM25 + hard structured filters.
- **Nine-factor ranking** with published weights and a reproducible score.
- **Explanations** derived from computed factors, never generated prose.
- **Outcome tracking, feedback, RBAC, audit logging, admin console.**

### Interface-only until credentials are supplied

- **BHASHINI ASR** — a real HTTP client exists; it raises `ProviderNotConfigured`
  without credentials rather than faking a transcript. Untested against live keys.
- **WhatsApp / IVR** — inbound webhook parsing works today and can be exercised
  at `POST /api/channels/{whatsapp,ivr}/inbound`. Outbound sending refuses
  without credentials instead of pretending a message was delivered.
- **LLM** — optional. With `LLM_PROVIDER=none` (the default) every user-visible
  string is deterministic. When enabled, the LLM may only fill gaps the rules
  left empty (inside a closed vocabulary) or rephrase existing lines; it can
  never originate an opportunity, qualification or scheme.

### Data provenance — read this before judging the numbers

The qualification, competency and opportunity records shipped here are
**representative demonstration data modelled on the NSQF / QP / NOS structure**.
They are not an authoritative extract. Every record carries a `source` and a
`last_verified_at` that the UI displays, precisely so this is visible rather
than assumed. Replace them with an authoritative feed before any real use.

**No government scheme is named or invented anywhere in this codebase.** The
guidance content is generic process advice, authored for this prototype and
labelled as such.

### Deliberate simplifications

- **SQLite by default.** Distance uses haversine in Python; vectors are stored as
  JSON and compared with numpy. PostgreSQL + PostGIS + pgvector is the intended
  production path and is isolated behind `core/geo.py` and `services/retrieval.py`.
- **The default embedder is a hashed n-gram vectoriser, not a neural model.** It
  captures lexical and morphological similarity and needs no download. Queries are
  expanded through the skill taxonomy before embedding, and vector similarity is
  blended with BM25 — which is what makes retrieval behave semantically without a
  neural model. Set `EMBEDDING_PROVIDER=sentence_transformers` for real embeddings.
- **Ranking weights are product judgement, not empirical findings.** They are
  published at `/api/system/ranking-config` with that caveat attached.
- **No claim of legal or regulatory compliance is made.** Consent, minimisation,
  access control, audit logging and deletion are implemented; they have not been
  reviewed against any specific regulation.

---

## The four phases

### Phase 1 — Understand
`Beneficiary → voice/text → ASR → language ID → dialect & code-switch handling → conversation understanding`

Adaptive slot filling, not a questionnaire: the engine asks only about the
highest-value fact still missing. Slots are configured in `app/core/slots.py`
and served to the client, so the frontend hardcodes no questions. Conversations
are interruptible and resumable. When ASR confidence falls below
`ASR_CONFIDENCE_THRESHOLD`, the turn is not committed — the assistant asks the
beneficiary to repeat or correct it.

Stored per turn: raw transcript, normalised text, detected language, language
confidence, ASR confidence, code-switch flag, source channel and timestamp.

### Phase 2 — Profile & Reason
`Conversation → profile extraction → skill normalisation → skill graph → skill-gap analysis`

The profile is a real domain model, not a JSON blob: `Education`, `Occupation`,
`Experience`, `Skill`, `Interest`, `Goal`, `Constraint` and `Location` are
separate, individually auditable rows.

**Self-reported ≠ verified.** Every skill carries `source`, `confidence`,
`proficiency` and `verification_status`, and the distinction survives all the
way to the UI. A spoken claim is `self_declared` and can never be promoted to
verified by the extractor — only training, assessment, certification or an
admin can do that.

### Phase 3 — Match & Personalise
`Profile → skill graph → skill gap → retrieval → filters → ranking → top pathways`

Hard gates applied before any scoring, each recorded with its reason:
inactive, expired, not yet open, unverified for over a year, no seats,
retired qualification standard, education not met, age out of range, beyond the
travel limit, and no overlap with the profile.

Nine ranking factors: skill fit, qualification fit, aspiration fit, gap
compatibility, location fit, mobility fit, availability, freshness and
verification. **Semantic similarity does not appear in the score at all** — it
selects the candidate pool; ordering comes from these explicit factors.

If nothing qualifies, the response is a first-class no-match: the closest
recognised pathway, the competencies missing for it, where to start, and
concrete ways to widen the search. Nothing is invented to fill the gap.

### Phase 4 — Measure & Learn
`Recommended → selected → enrolled → attending → completed → employed/self-employed`
(plus dropout, rejection, inactive opportunity, changed pathway)

Transitions are validated server side and append to an immutable history.
Objective events (`Outcome`) and subjective opinion (`Feedback`) are stored
separately so sentiment can never masquerade as evidence.

Outcome data **informs** future matching: it is surfaced in analytics and is the
intended input for re-tuning the ranking weights. There is no automatic online
learning here, and the code does not claim any.

---

## Repository layout

```
backend/
  app/
    api/            HTTP routes only - no business logic
    core/           enums, slot config, geo maths, rate limiting
    models/         SQLAlchemy ORM
    schemas/        Pydantic request/response contracts
    services/       the actual intelligence (see below)
    providers/      every external capability, behind an interface
    rag/            chunking and the ingestion pipeline
    seed/           taxonomy, qualifications and demo opportunities
  tests/            149 tests, including the 7 named demo cases
  alembic/          migrations
frontend/
  src/
    api/            typed client
    components/     shared UI
    pages/          beneficiary screens + admin console
    hooks/          speech recognition, async state
    i18n/           interface strings (en, hi, mr, ta)
docs/               architecture, assumptions, API guide, demo script
```

The services layer is where the product lives:

| Module | Responsibility |
|---|---|
| `language_id.py` | script detection, language ID, code-switch, normalisation |
| `lexicon.py` | multilingual extraction vocabulary |
| `skill_normalization.py` | free text → canonical taxonomy skill |
| `profile_extraction.py` | utterance → structured facts with evidence |
| `conversation_engine.py` | adaptive slot filling, confidence handling |
| `profile_service.py` | draft assembly and the confirmation gate |
| `skill_graph.py` | roll-up and transfer credit |
| `skill_gap.py` | per-competency coverage |
| `retrieval.py` | hybrid retrieval + hard filters + exclusion reasons |
| `ranking.py` | the nine factors and the relevance floor |
| `explanation.py` | factors → human-readable reasons |
| `recommendation.py` | orchestration, persistence, no-match path |
| `outcomes.py` | lifecycle and feedback |
| `analytics.py`, `audit.py` | admin insight and the audit trail |

---

## Testing

```bash
cd backend && python -m pytest -q          # 149 tests
cd frontend && npm run typecheck && npm run build
```

The seven demo cases from the problem statement are implemented as tests:

| Case | Test |
|---|---|
| 1 — low mobility prefers nearby | `test_case_1_low_mobility_prefers_nearby` |
| 2 — high mobility opens distant options | `test_case_2_high_mobility_opens_up_distant_options` |
| 3 — expired job must not appear | `test_case_3_expired_listing_never_appears` |
| 4 — ineligible qualification filtered | `test_case_4_ineligible_qualification_is_filtered` |
| 5 — low ASR confidence must confirm | `test_case_5_low_asr_confidence_asks_for_confirmation` |
| 6 — no match shows prerequisite path | `test_case_6_no_match_returns_prerequisite_pathway` |
| 7 — admin override must be logged | `test_case_7_override_is_recorded_in_the_audit_log` |

The seed data is built to exercise these: it deliberately contains an expired
batch, an inactive listing, a record unverified for 430 days, a retired
qualification standard, a graduate-only role, a high-fit job 149 km away, and a
tailoring unit 0 km away in an unrelated trade.

---

## Configuration

Everything is environment-driven; see `backend/.env.example` for the annotated
list. Nothing secret ever reaches the browser.

| Variable | Default | Why it matters |
|---|---|---|
| `DATABASE_URL` | SQLite file | Swap for a PostgreSQL DSN |
| `PROFILE_EXTRACTOR` | `rule_based` | `llm` enables LLM-assisted gap filling |
| `EMBEDDING_PROVIDER` | `local_hashing` | `sentence_transformers` for neural |
| `LLM_PROVIDER` | `none` | `anthropic` or `openai_compatible` |
| `SPEECH_PROVIDER` | `browser` | `bhashini` once credentials exist |
| `ASR_CONFIDENCE_THRESHOLD` | `0.65` | Below this, the system asks again |
| `STORE_RAW_AUDIO` | `false` | Audio is not persisted by default |
| `DEMO_MODE` | `true` | Gates the demo routes entirely |

Ranking weights live in `backend/config/ranking_weights.json` and are
hot-reloadable without a code change.

---

## Security and privacy

- JWT access/refresh tokens; role read from the database on every request, never
  from the token claim, so a tampered token cannot escalate.
- Registration **cannot** set a role — privileged accounts come only from
  `POST /api/admin/users`, which itself requires an admin.
- PBKDF2-HMAC-SHA256 at 600,000 iterations (OWASP 2023 guidance for PBKDF2).
- Per-user and per-IP rate limiting on authentication and conversation routes;
  account lockout after repeated failures.
- Identical error for unknown-email and wrong-password, so registered addresses
  are not enumerable.
- Purpose-scoped consent captured at registration and revocable at any time.
- Raw audio is not stored unless `STORE_RAW_AUDIO=true`; retention is configurable.
- Append-only audit log with actor, action, entity and before/after values;
  passwords, tokens and audio references are redacted before writing.
- `DELETE /api/auth/me` erases the account and everything cascading from it,
  leaving audit rows with the actor de-linked.
- The app refuses to boot with `ENVIRONMENT=production` while the development
  secret, `DEBUG`, or a wildcard CORS origin is still in place.

---

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit, and why
- [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) — every threshold and weight, with its justification
- [`docs/API.md`](docs/API.md) — endpoint reference
- [`docs/DEMO.md`](docs/DEMO.md) — the 3-minute walkthrough, step by step

---

## Licence and provenance

Built as a hackathon prototype. Demonstration data is synthetic and labelled as
such throughout. Before any deployment to real beneficiaries, replace the
qualification and opportunity data with authoritative sources, re-tune the
ranking weights against collected outcomes, and obtain a proper data-protection
review.
