# Architecture

## The shape of the problem

Existing ecosystems list courses, jobs and apprenticeships and let people search
them. That works for someone who already knows what they are looking for and can
read a listing. It fails the beneficiary this problem statement describes: a
10th-pass farmer who repairs pumps informally, wants to earn more, cannot travel
far, and would not think to type "agricultural equipment service technician"
into anything.

So the system inverts the direction. It starts from what the person can already
do — in their own words, in their own language — and works outward to what is
reachable.

```
VOICE → UNDERSTAND → PROFILE → SKILL GRAPH → SKILL GAP → RECOGNISED PATHWAY
      → LOCAL OPPORTUNITY → EXPLAIN → TRAINING/LIVELIHOOD → OUTCOME → FEEDBACK
      → BETTER FUTURE MATCHING
```

---

## Layering

```
┌──────────────────────────────────────────────────────────────┐
│ frontend/  React + TypeScript                                │
│   beneficiary screens (5)   ·   admin console (4 tabs)       │
└───────────────────────────┬──────────────────────────────────┘
                            │ typed JSON over HTTPS
┌───────────────────────────▼──────────────────────────────────┐
│ app/api/      routes only — parse, authorise, delegate       │
├──────────────────────────────────────────────────────────────┤
│ app/services/ the product: extraction, graph, gap, retrieval,│
│               ranking, explanation, outcomes, analytics      │
├──────────────────────────────────────────────────────────────┤
│ app/models/   SQLAlchemy ORM     app/schemas/  Pydantic      │
├──────────────────────────────────────────────────────────────┤
│ app/providers/  every external capability, behind a Protocol │
│   Speech · Messaging · Embedding · LLM · Opportunity · Qual  │
└──────────────────────────────────────────────────────────────┘
```

Two rules hold this together:

1. **No business logic in route handlers.** A route parses input, checks
   authorisation, calls a service and serialises the result. Ranking, extraction
   and gap analysis are therefore unit-testable without HTTP.
2. **Every external capability is a Protocol with an offline default.** The
   prototype never needs a network call, and a real provider drops in without
   touching business logic.

---

## Phase 1 — Understand

```
browser mic ──► Web Speech API ──► transcript + confidence ──┐
browser text ────────────────────────────────────────────────┤
WhatsApp webhook ──► adapter ──► InboundMessage ─────────────┤
IVR webhook ──────► adapter ──► InboundMessage ──────────────┤
                                                             ▼
                                            POST /conversation/{id}/message
                                                             │
                              ┌──────────────────────────────▼─────────┐
                              │ language_id: script → candidates →     │
                              │   marker words → language + confidence │
                              │   + code-switch flag                   │
                              └──────────────────────────────┬─────────┘
                                                             ▼
                              ASR confidence < threshold? ──► ask to repeat,
                                                              commit nothing
                                                             │
                                                             ▼
                                              profile extraction (Phase 2)
```

**Why recognition runs in the browser.** It is genuinely multilingual, works
offline from the server's point of view, needs no credential, and keeps audio on
the device. The trade-off is Chrome/Edge only — so text input is an equal path
on every screen, not a degraded fallback.

**The adaptive conversation.** `core/slots.py` declares each slot: priority,
whether it is required, its input type, its question in each language, its
options, and any dependency. Each turn the engine extracts what it can, folds it
into the draft, and asks about the highest-priority slot still unanswered whose
dependency is satisfied. The client renders whatever the server returns — adding
a language or reordering the conversation is a change to one file.

All state lives in `conversations.slots` and `conversations.draft_profile`,
which is what makes a dropped call resumable.

---

## Phase 2 — Profile & Reason

### Extraction

Two extractors behind one interface. The default is deterministic:

- `lexicon.py` — multilingual surface forms for education, occupation, mobility,
  goals, interests and constraints.
- `skill_normalization.py` — free text → canonical taxonomy skill.

Skill matching is **token-based, not substring**, because people do not speak in
dictionary form:

1. Tokenise; light-stem Latin tokens (plurals, gerunds). Indic tokens are left
   alone — naive suffix stripping on Devanagari does more harm than good.
2. Try aliases longest-first. A multi-word alias matches if all its tokens fall
   inside a small sliding window, in any order.
3. Consume matched positions, but allow a match that brings at least one *new*
   token.

Step 3 is what lets *"I repair pumps and farm machinery"* yield both
`pump_repair` and `farm_machinery_maintenance` from one shared verb, while
*"I repair tractors and there is an old pump in the field"* yields neither
falsely. Both are tested.

### The domain model

Not a JSON blob. `Education`, `Occupation`, `Experience`, `BeneficiarySkill`,
`Interest`, `Goal`, `Constraint` and `Location` are separate rows, each with its
own source, confidence and — where meaningful — verification status.

**Self-reported is never conflated with verified.** A spoken claim is
`self_declared`. Only training completion, assessment, certification or an admin
can promote it. `apply_draft` preserves admin- and assessment-verified skills
even when a beneficiary re-runs the whole conversation.

### The skill graph

```
        pump repair (0.75, direct)          farm machinery maintenance (0.75, direct)
             │                                   │
    ┌────────┼────────┐                 ┌────────┼────────┬──────────┐
    ▼        ▼        ▼                 ▼        ▼        ▼          ▼
 motor   irrigation  solar          tool     engine   diagnostics  hydraulics
rewinding operation   pump        handling  maintenance
 (0.38)    (0.38)    (0.34)        (0.53)    (0.45)     (0.38)      (0.30)
                    ▲
            "partly transfers from pump repair (45% credit)"
```

Two edge kinds: parent roll-up (0.7 per level) and typed transfer edges
(authored weights, one hop). Every derived node records *how* it was derived,
in words — which is what lets the explanation layer say why someone partly
covers a competency they never claimed.

### The gap engine

```
coverage(competency) = max over evidencing skills of (skill_score × link_coverage)
covered ≥ 0.60   partial ≥ 0.30   missing < 0.30
```

Maximum rather than sum: three weakly related skills must not add up to a
competency nobody has demonstrated.

For Ravi against *Agriculture Equipment Service Technician (AGR/Q1101)*:

| Competency | Result |
|---|---|
| Routine maintenance of agricultural equipment | **covered** |
| Repair pumps and irrigation equipment | **covered** |
| Diagnose faults in agricultural machinery | partial |
| Advanced repair of engines and transmission | partial |
| Test and commission repaired equipment | **missing** |
| Maintain workplace health and safety | **missing** |
| Interact with customers and keep service records | **missing** |

Which is exactly the shape the problem statement describes: equipment
maintenance and pump repair present; diagnostics, safety, testing and advanced
repair to learn.

---

## Phase 3 — Match & Personalise

```
profile + skill graph
        │
        ▼
  query construction ── expanded through the skill taxonomy
        │                (aliases, parents, transfer targets)
        ▼
┌───────────────────────────────────────────────────────────┐
│ HARD FILTERS — applied before any scoring                 │
│  inactive · expired · not yet open · unverified > 1 year   │
│  no seats · retired qualification · education not met      │
│  age out of range · beyond travel limit                   │
│  → each exclusion recorded with its reason                │
└───────────────────────┬───────────────────────────────────┘
                        ▼
      vector similarity (0.6) ⊕ BM25 (0.4)  → candidate pool
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│ RANKING — nine factors, weighted mean, no similarity      │
│  skill fit · qualification fit · aspiration fit           │
│  gap compatibility · location fit · mobility fit          │
│  availability · freshness · verification                  │
└───────────────────────┬───────────────────────────────────┘
                        ▼
        relevance floor → diversification → top 3
                        ▼
              explanation built from the factors
```

**Why similarity does not enter the score.** Vector scores are min-max
normalised across whatever was retrieved, so blending them in would make one
person's "skill fit" move depending on what else happened to be in the pool.
Unstable, and impossible to explain honestly to a beneficiary. Similarity picks
the pool; the nine factors decide the order.

**Why retrieval is hybrid anyway.** Pure vector search on a local lexical
embedder misses precise occupational vocabulary; pure keyword search misses
morphological variants. Taxonomy expansion plus both scorers covers each other's
gaps, and none of it can invent a record — every candidate is a row that passed
every hard filter.

**Diversification.** At most two of one opportunity type and one per provider
while alternatives exist. Three near-identical listings from one centre is
technically well-ranked and practically useless.

**The no-match path is first-class.** When nothing qualifies:

```
"No verified suitable opportunity was found: <the dominant reason>."
  → closest recognised pathway (a qualification standard, not a listing)
  → the competencies missing for it
  → where to start
  → concrete retry options (widen radius, check education, change goal)
```

Nothing is substituted in to fill the space.

---

## Phase 4 — Measure & Learn

```
RECOMMENDED → SELECTED → ENROLLED → ATTENDING → COMPLETED → EMPLOYED
                  │          │          │           │      ↘ SELF_EMPLOYED
                  ▼          ▼          ▼           ▼
              REJECTED   DROPPED_OUT  DROPPED_OUT  CHANGED_PATHWAY
```

Transitions are validated server side against an explicit table; an invalid
request returns 409 naming the allowed next steps. Every change appends to an
immutable `status_history` with actor and timestamp.

`Outcome` (what happened) and `Feedback` (what the person thought) are separate
tables on purpose. Rejection reasons are a closed vocabulary, so they aggregate
into something actionable instead of a pile of free text.

---

## Grounding: how a claim stays checkable

```
Opportunity row ──► rag/ingest.py ──► KnowledgeDocument ──► KnowledgeChunk
  (source, verified_at)                (entity_type, entity_id)   (embedding,
                                                                   metadata)
                                              │
                          retrieval ──────────┘
                              │
                              ▼
            every retrieved chunk resolves back to the row it came from
```

Chunks are generated from structured records the system already holds, not
scraped PDFs, and each keeps a back-link to its source row. That back-link is
what makes grounding checkable rather than asserted: anything shown to a
beneficiary can be traced to a record with a source, a verification status and
a verification date — all of which the UI displays.

When an LLM is enabled it may only rephrase already-computed lines, and its
output is discarded if it changes the line count or introduces a number that
was not there. It can never originate an opportunity, qualification or scheme.

---

## Persistence

SQLite by default so the prototype runs with zero infrastructure. Three
deliberate isolations make PostgreSQL a configuration change plus two swaps:

| Concern | Now | Production |
|---|---|---|
| Distance | haversine in `core/geo.py` | PostGIS `ST_DWithin` on `geography(Point,4326)` |
| Vectors | JSON column + numpy cosine | `pgvector` `vector(dim)` + HNSW index |
| Keyword | in-process BM25 | `ts_rank_cd` over a tsvector column |

All three are confined to `services/retrieval.py` and `core/geo.py`.

One SQLAlchemy subtlety worth recording: `Conversation.slots` and
`draft_profile` are wrapped in `MutableDict`. Without it, mutating the loaded
dict in place makes the old and new values compare equal at flush time and
SQLAlchemy skips the UPDATE entirely — a silent data-loss bug that cost real
debugging time here.

---

## Security model

```
request ──► HTTPBearer ──► decode JWT ──► load user from DB
                                             │
                                  role read from the ROW,
                                  never from the token claim
                                             │
                        token_version must match (revocation)
                                             ▼
                             require_roles(...) per endpoint
```

- Registration cannot set a role. `RegisterRequest` has no `role` field and the
  handler assigns `beneficiary` literally. Privileged accounts come only from
  `POST /api/admin/users`, which requires an admin.
- Ownership is checked on every beneficiary-scoped read; a non-owner gets 404,
  not 403, so ids are not confirmed to exist.
- Demo routes are disabled unless `DEMO_MODE=true` and refuse outright under
  `ENVIRONMENT=production`. The demo reset can only ever mint a session for one
  fixed non-privileged account, and asserts that account's role before issuing.

---

## Failure behaviour

| Failure | Response |
|---|---|
| ASR unavailable / unsupported browser | text input, stated plainly |
| ASR low confidence | ask to repeat or correct; commit nothing |
| LLM unavailable | deterministic extraction and templates (the default path) |
| Knowledge index empty | fall back to the record's own text; flag `used_vector: false` |
| Opportunity source unreachable | cached verified records with their last-verified date |
| GPS unavailable or denied | manual village / PIN entry |
| Database unreachable | 503 with a plain-language message, logged server side |
| Nothing qualifies | first-class no-match with a prerequisite pathway |

The principle throughout: degrade to something true, and say what happened.
