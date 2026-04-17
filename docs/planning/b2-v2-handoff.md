# B.2 v2 — Phase 2c handoff for next session

**If you are a new Claude session picking this up**: read this file
first, then `b2-v2-design.md`, `b2-v2-phase1-validation.md`
(§ 8-10 for the Phase 2a-b measurements), `b2-v2-phase2b-ledger.md`
(curation patterns + deferred decisions), and
`b2-v2-query-portfolio.md` in that order. That gives full
methodology context + the current open-prediction state.

## Branch state

- **Branch**: `feat/multilingual-regression-v2` (branched from `main`,
  un-pushed)
- **Exploratory branch**: `feat/multilingual-regression-mvp`
  (preserved as reference for why broad-tag MVP failed; un-pushed)

## Phase progress

| Phase | State | Deliverable |
|---|---|---|
| 1 | ✅ | caching × ko × 4 genres; dense/BM25 asymmetry + anchor mechanism validated |
| 2a | ✅ | caching × en × 4 genres; EN parity confirmed |
| 2b | ✅ | postgres × 4 genres × 2 langs = 32 chunks; topic-strong pipeline invariance identified (B-2) |
| **2c** | **🔄 next** | **cost_optimization × 4 genres × 2 langs (first topic-weak prediction test)** |
| 2d onwards | 📋 | 12 remaining topics × 8 batches each, cadence below |
| 3-7 | 📋 | full curation (per-topic drift), query portfolio, calibration, CI wiring, PR |

## Phase 2c first actions (in order)

1. **Read Phase 2b measurement artifacts** if new session:
   - `b2-v2-phase1-validation.md` § 10 — postgres sensitivity numbers
     + pre-registered matrix outcome
   - `b2-v2-phase2b-ledger.md` — curation category breakdown +
     observations + deferred decisions
   - `b2-v2-design.md` § "Topic-strong vs topic-weak" — the
     prediction set Phase 2c starts validating

2. **Generate `cost_optimization` cells** (topic-weak prediction
   test #1). 8 Gemini batches = 4 genres × 2 languages. Selected
   first because cost_optimization has natural ADR-heavy subject
   matter (explicit cost trade-offs) — sharpest genre rotation
   expected. Use `b2-v2-gemini-template.md` with:
   - `TOPIC: cost_optimization`
   - `GENRE`: varies per batch (runbook, postmortem, adr,
     troubleshooting)
   - `LANGUAGE`: varies per batch (ko, en)
   - Include the same "Drift to avoid" block from Phase 2b prompts

3. **Curate (Phase 3a)** each returned batch before markdown
   conversion. Expected drift rate ~30% based on three prior
   topics. Log corrections under
   `b2-v2-phase2b-ledger.md` § "Curation ledger" (append new topic
   section; don't rewrite existing entries).

4. **Sensitivity spot-check** on cost_optimization 32 chunks.
   Expected outcome (topic-weak prediction): divergence 6-8/8 KO,
   5-7/8 EN. If instead divergence ≤ 2/8, cost_optimization falls
   into topic-strong despite prediction — record and continue; the
   prediction is pre-registered, not assumed.

5. **Generate `security` cells** (topic-weak prediction test #2).
   Second because security has `incident` as a subtopic, which may
   bias postmortem dominance — establishing the cost_opt pattern
   first reduces interpretation risk.

6. **Generate `kafka` cells** (first topic-strong **boundary** test,
   not clean confirmation). Kafka has proper-noun-heavy API
   vocabulary like postgres/k8s but more conceptual narrative
   (backpressure, at-least-once semantics, consumer lag design).
   This is the informative case: depending on divergence,
   topic-strong criterion refines to "proper-noun density" vs
   "proper-noun + procedure density" vs "needs revision".

7. **Generate `k8s` cells** (topic-strong clean confirmation).
   Expected: divergence 0-2/8, similar to postgres. If so, the
   topic-strong hypothesis graduates from "validated on 1 topic" to
   "validated on 2 topics with boundary context from kafka".

8. **Remaining 9 topics** in any order — observability, ci_cd, auth,
   networking, kafka-adjacent (streams), ml_ops, data_pipelines,
   incident_response, api_design. Most expected to be middle (3-5/8
   divergence); surprises feed back into the topic-strong/weak
   vocabulary profile.

9. **After topic 5** (= postgres + 4 more): implement Phase 3b drift
   validator rule tiers from the accumulated ledger. Earlier than
   that risks fitting rules to a biased sample.

10. **Phases 4-7** proceed once the 15-topic corpus is complete. Query
    portfolio final draft with topic-weak floor activation and
    topic-strong floor demotion happens at Phase 4.

## Key invariants (do not drift from these)

- Topic vocabulary is frozen at 15 topics (see `b2-v2-design.md`).
  No additions without explicit plan update.
- Subtopic vocabulary is in "emergent + mid-way freeze" mode; freeze
  target after ~80 chunks total. Currently 64 (caching 32 + postgres
  32). Freeze trigger arrives during cost_optimization generation —
  plan to lock subtopic list after cost_opt batches return.
- Genre-primary queries are a **required** Phase 4 axis (not deferred
  memo). Portfolio: 100 queries per language.
- KO is primary regression signal; EN is parity + best-effort.
- Do NOT introduce cross-cutting tags (`performance`,
  `data_consistency`, `high_availability`) — absorb into existing
  topic subtopics per `b2-v2-design.md` rules.
- Every fixture commit includes the `> Synthetic content for search
  regression testing — verify before adopting as runbook.` disclaimer
  at the top of the file.
- Curation (Phase 3a) is **mandatory human-in-the-loop**, not
  optional. Raw Gemini output has ~30% drift rate.
- AI attribution opt-in: include `Co-Authored-By: Claude` in commits
  per user's prior explicit approval for v2 PR work. Check with user
  before continuing this policy if Phase 2c generation spans a long
  pause.

## Locked decisions from Phase 2b (do not revisit without cause)

These are pre-registered commitments from the Phase 2b decision
process. They reduce rework if Phase 2c or later topics produce
similar stop-gates.

- **B-2 preference** (accept as pipeline-invariant subset) is the
  default response to any topic that produces divergence ≤ 3/8 with
  weak cross-topic bleed (< 10%). B-1 (halt + redesign) activates
  only if bleed ≥ medium. B-3 (regenerate corpus) is rejected.
- **Pre-experiment interpretation matrix** for any topic showing
  stop-gate results: lock the hypothesis predictions before
  running experiments so results read off a cell, not fit a
  narrative. See `b2-v2-phase1-validation.md` § 10.4 for the
  postgres example.
- **Query fairness rule**: strengthened queries must match the
  caching baseline on token count (± 15%) and IDF-weighted token sum
  (± 15%) to exclude "weak query" as a confound.
- **Genre-pair confusability predictions** (ADR↔postmortem,
  runbook↔troubleshooting) stay pre-registered until Phase 5
  confusion matrix either confirms or refutes them. Current evidence:
  runbook↔troubleshooting has 1 consistent miss in ko postgres
  (2/2 runs); ADR↔postmortem has 0 evidence so far.
