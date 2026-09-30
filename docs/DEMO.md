# Demo walkthrough — Ravi

A 3-minute run for a judge. It needs no network, no API key and no external
service. Every screen below is driven by the same code path a live user takes.

---

## Before you start

```bash
cd backend && uvicorn app.main:app --port 8000     # terminal 1
cd frontend && npm run dev                          # terminal 2
```

Open **http://localhost:5173** in **Chrome or Edge** (voice input needs the Web
Speech API; everything also works by typing).

> If you want the whole thing in a terminal instead, `python -m app.cli demo`
> prints every stage, including the ranking computed at both low and high
> mobility.

---

## The narrative

**Ravi** — 10th pass, works in agriculture, repairs pump sets informally, has
some farm-machinery experience, likes mechanical work, cannot travel far, wants
to earn more and would prefer to work for himself.

---

## 1. Opening — press "Try Ravi Demo"

Resets the demo beneficiary, signs you in as him, and opens a conversation.

Say out loud what the screen is *not* doing: no account setup, no form, no
category picker.

> Ravi's location is pre-set, because speech cannot supply coordinates.
> Everything else is extracted live.

## 2. Ravi speaks (~30s)

Press **"Say line 1"** (or speak it yourself, or type it):

> *"I work in agriculture and I repair pumps sometimes. I want to earn more.
> I like mechanical work but I cannot travel very far."*

Watch the assistant reply with **one** follow-up question, not a form. It asks
only about what is still missing — education, in this case.

Lines 2 and 3 add duration, schooling and the goal:

> *"I have been repairing pumps and farm machinery for about 5 years. I am 10th pass."*
> *"I would prefer to start my own work rather than a job."*

**Point out:** the progress bar. The system tracks which high-value facts it
still needs, and stops asking once it has them.

*Optional, 10 seconds:* switch the language selector to हिन्दी and type
*"मैं खेती का काम करता हूँ और कभी कभी पंप ठीक करता हूँ"* — the same pump-repair
skill is extracted from Devanagari. Code-switching works too.

## 3. "We understood you as…" (~25s)

Press **"I have told you everything"**.

| Field | Extracted |
|---|---|
| Education | 10th standard |
| Current work | Agriculture / farm work · Machinery repair |
| Skills | Pump repair · Farm machinery maintenance (+ areas of work) |
| Interests | Mechanical |
| Goal | Higher income · Self-employment |
| Travel | Only near my village |

**The two things to point at:**

1. Every skill is chipped **"You told us"** — self-reported, not verified. The
   system never promotes a spoken claim to a certified one.
2. Every row is editable, and nothing has been written to Ravi's real profile
   yet. This screen is the consent gate.

Press **"This is correct"**.

## 4. Your possible pathways (~40s)

Three cards, with match strength, distance, what is left to learn, availability,
and *why*.

Expected at low mobility:

| # | Pathway | Distance | Gap |
|---|---|---|---|
| 1 | Agriculture Equipment Service Technician — Training | ~12 km | moderate |
| 2 | Village Pump & Farm Machinery Repair — Micro-Enterprise | ~3 km | large |
| 3 | Agricultural Machinery Operator — Training | ~9 km | large |

**Now the important bit — open "Why some options are not shown".**

This is the difference between a recommender and a search box:

- *Farm Machinery Maintenance — batch closed* → **expired**
- *Agri-Business Extension Associate* → **requires a degree**
- *Pump Set Operator Certification (legacy)* → **built on a retired standard**
- *Farm Machinery Helper* → **position filled**
- *Equipment Maintenance Refresher* → **not re-verified for over a year**
- *Tailoring Unit* → **0 km away, but unrelated to anything Ravi told us**
- *Mechanical Technician, Pune* → **149 km, beyond his travel limit**

Nothing was quietly dropped; every exclusion states its reason.

## 5. Change the travel limit (~20s)

Press **"I can travel further or move"**.

The ranking **changes**: options 22–28 km away now out-rank the 3 km enterprise
pathway, and the 149 km Pune job is no longer excluded on distance — it appears
in the considered set instead.

> This is the proof that ranking is not embedding similarity. The profile did
> not change. One constraint did, and the order moved.

Note the radius text updates from 25 km to 200 km, and that changing mobility
here does **not** rewrite Ravi's stored profile — it is a what-if.

## 6. Why this one? (~30s)

Open pathway **1**.

- **Why this fits** — skill overlap, eligibility and level step, what he said he
  wants, distance, travel needed.
- **What you need to learn** — Test and commission repaired equipment ·
  Maintain workplace health and safety · Interact with customers and keep
  service records, each with its NOS-style code.
- **How this was scored** — all nine factors with score × weight. The headline
  number is reproducible from them (there is a test asserting exactly that).
- **Source** and **last verified** date, shown plainly.

**Say:** none of this is generated prose. Each line is derived from a computed
factor, which is why the explanation cannot drift away from the score.

## 7. Choose and track (~20s)

Press **"Choose this pathway"** → the progress screen.

`Chosen → Enrolled → Attending → Completed → Working`

Press **Enrolled**. The lifecycle advances and the history records who changed
what, when. Try an invalid jump and the server refuses it with the allowed next
steps named.

Below, feedback is collected separately from the lifecycle — objective events
and subjective opinion are different facts.

## 8. Admin view (~30s)

Sign out, sign in as `admin@navigator.example.com` / `Admin@12345`, open
**Administration**.

- **Overview** — banner states plainly that these are demonstration figures.
  Data-quality counts: verified, needing re-verification, expired, excluded as
  stale.
- **Opportunities** — verify a listing (extends validity, stamps who checked it),
  or import a CSV. Import runs as a **dry run first** and reports every row it
  would reject. Imported records arrive as **draft** and **unverified** —
  importing is not verifying.
- **Beneficiaries & AI review** — open Ravi. Every conversation turn is shown
  with detected language, language confidence, ASR confidence, code-switch flag,
  and exactly which skills were extracted from it. A counsellor can correct the
  profile.
- Scroll to his recommendations → **Review** → **Reject** with a reason.
- **Audit trail** — filter to *Recommendation overrides*. The action is there
  with the actor, the role, the timestamp and before/after values. Expand
  "before / after".

Then go back to Ravi's account: the rejected pathway can no longer be selected.
**AI recommendation does not automatically become truth.**

## 9. Close

Open **http://localhost:5173/system**.

Every provider with its real state: what is active, what is interface-only, what
is not configured. Ranking weights published with the caveat that they are
product judgement, not validated figures. Known limitations listed.

> *"From aspiration to livelihood, not just recommendation."*

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| Microphone button missing | You are not in Chrome/Edge. Type instead — the demo is identical. |
| Mic permission denied | Allow it in the address bar, or type. |
| "Demo data has not been seeded" | `cd backend && python -m app.cli seed` |
| Pathways page empty | Confirm the profile first; recommendations need a confirmed profile and a location. |
| Want a clean slate | `cd backend && python -m app.cli reset --yes` |

---

## What to claim, and what not to

**Do say:**
- Voice input, language ID and code-switch handling work now, offline.
- Extraction, skill graph, gap analysis and ranking are deterministic and tested.
- Every recommendation is a verified record that passed every hard filter.
- Every exclusion has a stated reason.
- Outcome data is collected and informs future matching.

**Do not say:**
- That the qualification data is an authoritative NSQF extract — it is
  representative sample data, and the UI says so.
- That BHASHINI is integrated — the adapter exists and is inert without credentials.
- That WhatsApp or IVR are live — inbound parsing works; sending needs credentials.
- That the weights are validated — they are product defaults awaiting real
  outcome data.
- Any real-world impact number. The analytics banner already says these are
  demonstration figures.

The honesty is not a hedge. It is the part a judge can verify, and it is what
separates this from a demo that falls apart under one question.
