# Assumptions, thresholds and their justification

Every number in this system that could have been chosen differently is listed
here with the reasoning behind it. None of these are empirical findings. They
are product judgements made so the system behaves legibly and conservatively,
and they are the first things that should be re-tuned against real outcome data.

---

## 1. Data provenance

| Data | What it actually is |
|---|---|
| Qualifications (`AGR/Q1101` etc.) | **Representative samples** modelled on the NSQF / QP / NOS structure. Realistic in shape, not extracted from an authoritative register. |
| Competencies (`AGR/N1101` etc.) | Same — modelled on the NOS pattern. |
| Opportunities | Curated demonstration listings for Nashik district, Maharashtra. Providers and coordinates are plausible but synthetic. |
| Guidance documents | Generic process advice authored for this prototype. **No government scheme is named or described anywhere.** |
| Skill taxonomy | Authored for this prototype, covering agriculture, mechanical, electrical, safety and enterprise skills with multilingual aliases. |

Every record carries `source` and `last_verified_at`, and both are shown in the
UI. This is deliberate: a judge or a beneficiary should be able to see the
provenance rather than infer authority from confident presentation.

---

## 2. Skill scoring

### Proficiency → score
```
none 0.0 · basic 0.45 · intermediate 0.75 · advanced 1.0
```
An evenly spaced scale would treat "basic" as a quarter of "advanced", which
understates the value of practical competence. Basic sits at 0.45 because
someone who can already do a task unsupervised — however roughly — is closer to
halfway than to nothing.

### Direct skill score
```
proficiency_score × (0.55 + 0.45 × confidence_score)
```
Confidence modulates but cannot erase a claim: even a low-confidence extraction
retains 55% of its proficiency value. Silently discounting what someone told us
about themselves would be both rude and wrong.

**Verification status is deliberately *not* multiplied in here.** An unverified
skill is still real competence. Verification is scored separately (as the
`verification` ranking factor) and displayed separately, so the UI can say "you
have this, but it is not certified yet" instead of quietly halving the person's
ability.

### Proficiency inference from speech
| Signal | Result |
|---|---|
| ≥ 6 years stated | advanced |
| ≥ 2 years stated | intermediate |
| "daily", "regularly", "रोज" | intermediate |
| anything else | basic |
| "sometimes", "कभी कभी" (and no stated duration) | capped at basic |

Deliberately conservative. Overstating someone's level pushes them into training
they are not ready for, or filters out training they actually need.

### Roll-up and transfer
- **Parent roll-up: 0.7 per level.** Holding "pump repair" implies real but
  partial standing in "mechanical work".
- **Transfer edges: one hop only.** Chaining transfers would let weak
  relationships compound into competence nobody demonstrated.
- **Transfer weights (0.35–0.7)** are authored per edge in
  `seed/data/skill_relations.json` — for example pump repair → motor rewinding
  at 0.5, farm machinery maintenance → tool handling at 0.7.
- A derived score can never exceed its source. Enforced by test.

---

## 3. Skill-gap bands

### Competency coverage
```
coverage = max(skill_score × link_coverage)   -- over the skills evidencing it
```
**Maximum, not sum.** Summing would let three weakly related skills add up to a
competency the person has never demonstrated.

| Band | Threshold | Meaning |
|---|---|---|
| covered | ≥ 0.60 | can likely already do this |
| partial | ≥ 0.30 | real transferable ground, not sufficient alone |
| missing | < 0.30 | has to be learned |

0.60 rather than a rounder 0.5 or 0.75: someone at intermediate proficiency on a
skill that fully evidences a competency scores 0.75 and clears it, while
someone at basic proficiency scores 0.45 and does not. That is the intended
line.

### Overall gap band — thirds
```
small ≤ 1/3 · moderate ≤ 2/3 · large > 2/3
```
A principled split rather than tuned constants.

---

## 4. Mobility → travel radius

| Band | Radius |
|---|---|
| low | 25 km |
| medium | 60 km |
| high | 200 km |

These are **product defaults, not measured travel behaviour.** 25 km is roughly
the distance a rural worker can reach and return from within a day by local
transport without paid accommodation. They are configurable per deployment in
`config/ranking_weights.json`, and a beneficiary can override their own limit.

**The radius is a hard gate, not just a scoring factor.** A person who cannot
travel cannot travel, and presenting an unreachable option as a recommendation
wastes their time. Within the radius, distance is a graded factor. Anything
excluded on distance is reported with that reason, and the no-match path offers
an explicit "search a wider area" — widening is always the user's decision, never
silent.

### Location fit curve
Full marks within a quarter of the radius, decaying linearly to zero at the
edge. Unknown distance scores a neutral **0.5, not 0** — a record with missing
coordinates should not be silently buried.

---

## 5. Ranking weights

| Factor | Weight | Why |
|---|---|---|
| skill fit | 0.26 | the strongest single predictor of success, but under a third so it cannot dominate |
| qualification fit | 0.16 | eligibility is close to binary; the level step matters |
| aspiration fit | 0.14 | what the person said they want is not a tiebreaker |
| location fit | 0.14 | deliberately equal to aspiration — distance is a first-class constraint, not an afterthought |
| gap compatibility | 0.10 | rewards a gap worth closing and realistic to close |
| mobility fit | 0.08 | the travel band on top of raw distance |
| availability | 0.06 | seats matter, but a full course is already hard-filtered |
| freshness | 0.04 | stale records are mostly handled by hard filters |
| verification | 0.02 | small, because unverified records are already penalised elsewhere |

Weights are normalised at scoring time, so they need not sum to 1. The final
score is reproducible from the published per-factor scores — enforced by
`test_match_score_equals_weighted_mean_of_factors`.

**Semantic similarity carries zero weight.** It decides which candidates are
retrieved; ordering is decided by these nine explicit factors. An earlier draft
blended a pool-normalised similarity into skill fit, which made one person's
"skill fit" change depending on what else happened to be retrieved — unstable,
and impossible to explain honestly. It was removed.

### Ideal gap ratio: 0.35
Gap compatibility peaks at a 35% gap. A zero gap means no progression; a very
large gap means the person is not ready yet. Roughly a third to learn is the
shape of a worthwhile, achievable next step.

### Relevance floor: 0.15
A candidate must connect to something the beneficiary actually told us — skill
overlap, qualification coverage, or an explicit interest. Below that it is
excluded with reason `NO_PROFILE_OVERLAP`.

This exists because of a real failure found during development: a tailoring
enterprise 0 km away, active and verified, out-ranked relevant mechanical
pathways purely on proximity and availability. Proximity plus availability
without relevance is a coincidence, not a recommendation.

### Minimum score: 0.28
Below this a candidate is not presented at all. Better a no-match with a
prerequisite pathway than a weak suggestion dressed up as advice.

---

## 6. Freshness

| Threshold | Effect |
|---|---|
| 90 days | flagged stale; loses freshness points; surfaces in the admin review queue |
| 365 days | **hard excluded** with reason `STALE_UNVERIFIED` |

A listing nobody has confirmed in a year is not evidence that a place exists.
Sending someone on a bus journey to a course that closed months ago is a real
harm, and freshness is cheap to check.

---

## 7. Conversation

- **ASR confidence threshold: 0.65.** Below it, the turn is not committed —
  the assistant asks the beneficiary to repeat or correct it. Set low enough
  that the system does not nag, high enough that a misheard skill never silently
  enters the profile.
- **Browsers that omit a confidence value** are assigned 0.8 — a neutral
  stand-in above the threshold. It is never presented to the user as a measured
  figure.
- **Slots are asked at most once.** If a beneficiary does not answer, the
  conversation moves on rather than looping.
- **Nothing reaches the profile until explicit confirmation.** The draft lives
  on the conversation row; `POST /conversation/{id}/confirm` is the only path
  from draft to profile.

---

## 8. Language identification

Unicode script detection narrows the candidates; marker words disambiguate
languages sharing a script (Hindi vs Marathi in Devanagari) and detect
romanised Indic typed in Latin script.

- **Code-switching is flagged at ≥ 10% minority script.** Below that it is
  usually a stray English technical word, not genuine mixing.
- **Confidence is reported honestly.** When the signal is weak the method says
  so, which is what lets the conversation engine ask rather than assume.
- A heuristic was chosen over a statistical model deliberately: it is
  inspectable, needs no download, and its failure modes are predictable.

---

## 9. Retrieval

- **Vector 0.6 / BM25 0.4.** Keyword matching is weighted heavily because
  occupational vocabulary is precise — "pump" really does mean pump.
- **Candidate pool: 60.** Ample for a district-scale dataset.
- **Query expansion runs over the skill taxonomy** (aliases, parents, transfer
  targets), not over a language model. This is what makes a lexical retriever
  behave semantically without a neural model, and it is inspectable.
- **Bounding-box prefilter only above 500 records.** Below that every record is
  evaluated so each exclusion carries its true reason instead of a generic
  "out of range". On PostgreSQL this becomes a single `ST_DWithin`.

---

## 10. Known limitations

1. **The default embedder is lexical, not neural.** It will not match a
   paraphrase with no shared vocabulary. Taxonomy expansion and BM25 mitigate
   this; `sentence_transformers` removes it.
2. **The extraction lexicon is hand-authored.** Coverage is strongest in
   English and Hindi, good in Marathi and Tamil, thinner elsewhere. An unknown
   phrasing is silently not extracted — the conversation then asks about the slot
   directly, which is the intended fallback.
3. **Geocoding is not implemented.** A typed village name is stored but does not
   produce coordinates; distance ranking needs GPS or a seeded location. A
   production build needs a PIN-code/village gazetteer.
4. **BHASHINI is untested against live credentials.**
5. **Distance is great-circle, not travel time.** A 20 km hill route and a 20 km
   highway are not the same journey.
6. **No online learning.** Outcome data is collected and surfaced; re-tuning the
   weights from it is a deliberate manual step.
7. **The rate limiter is in-process.** Multi-worker deployment needs Redis.
8. **No compliance review has been performed.** Privacy controls are implemented
   and documented, but not assessed against any specific regulation.
