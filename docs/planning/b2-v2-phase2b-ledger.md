# B.2 v2 — Phase 2b ledger (process log)

Process log for the postgres topic. Curation decisions, observations
collected, and deferred decisions that surfaced during Phase 2b. Lives
as a companion to `b2-v2-design.md` (timeless methodology) and
`b2-v2-phase1-validation.md` (measurement snapshots). This file
accumulates new entries as later topics are generated; existing entries
are not rewritten.

## Curation ledger — Phase 2b postgres (9 drift corrections / 32 chunks)

Drift rate 9/32 ≈ 28%, consistent with Phase 1 (caching ko) and Phase
2a (caching en) at ~30%. Gemini output requires curation as a
first-class pipeline step; see `b2-v2-design.md` § "Implementation
phases" for the 3a/3b split.

### Category distribution

| Category | Count | Description |
|---|---|---|
| Out-of-vocab expansion | 1 | Gemini used a subtopic outside the closed vocabulary (e.g. `search/cluster` on a postgres replication chunk) |
| Intra-vocab misclassification | 4 | Valid subtopic, wrong cell (e.g. `k8s/networking` where `k8s/scaling` fit the HPA content) |
| Absent-topic projection | 3 | Subtopic not supported by the chunk body (e.g. `postgres/vacuum` tagged on a replication runbook that never mentions vacuum) |
| Claude over-correction | 1 | Curator rejected a valid Gemini secondary that the chunk body actually supported (troubleshooting ko vacuum: `cost_optimization/storage` was correct; handoff's initial "drop" proposal was the over-correction) |

The fourth category matters as much as the first three. Curation
itself is a failure mode — if only under-correction is tracked,
curator bias accumulates and the corpus drifts toward canonical-looking
but less realistic tagging. Phase 5 calibration should verify that
curator over-correction rate remains bounded.

### Per-chunk corrections (Phase 2b postgres, 9 total)

| Batch | Chunk | Original secondary | Final secondary | Category |
|---|---|---|---|---|
| runbook EN | #1 indexing | `[postgres/vacuum, cost_optimization/compute]` | `[observability/metrics]` | Absent-topic projection |
| runbook EN | #2 partitioning | `[postgres/indexing, data_pipelines/transformation]` | `[data_pipelines/ingestion]` | Out-of-vocab expansion (transformation=ETL) |
| runbook EN | #4 replication | `[postgres/vacuum, incident_response/mitigation]` | `[incident_response/mitigation]` | Absent-topic projection |
| troubleshooting KO | #1 vacuum | `[observability/metrics, cost_optimization/storage]` | `[observability/metrics, cost_optimization/storage]` **kept** | Initial handoff proposal was over-correction; reverted |
| troubleshooting KO | #2 conn_pool | `[observability/alerting]` | `[observability/metrics]` | Intra-vocab misclassification |
| troubleshooting KO | #3 indexing | `[search/query, observability/tracing]` | `[observability/metrics]` | Out-of-vocab (search/* = ES vocab) + Intra-vocab (tracing≠metrics) — counted once as Out-of-vocab |
| postmortem KO | #1 vacuum | `[observability/alerting]` | `[incident_response/mitigation]` | Intra-vocab misclassification |
| postmortem KO | #3 indexing | `[observability/metrics]` | `[observability/logging]` | Intra-vocab misclassification |
| adr KO | #1 partitioning | `[cost_optimization/storage]` | `[data_pipelines/orchestration]` | Absent-topic projection |
| adr KO | #3 indexing | `[postgres/vacuum]` | `[cost_optimization/storage]` | Absent-topic projection |
| adr KO | #4 replication | `[incident_response/mitigation]` | `[observability/metrics]` | Absent-topic projection (mitigation) → replaced with body-supported metrics |
| postmortem EN | #3 conn_pool | `[k8s/networking]` | `[k8s/scaling]` | Intra-vocab misclassification (HPA=scaling) |
| postmortem EN | #4 replication | `[search/cluster]` | `[incident_response/mitigation]` | Out-of-vocab expansion |
| troubleshooting EN | #3 replication | `[networking/load_balancing]` | `[observability/metrics]` | Absent-topic projection (LB never mentioned) |
| troubleshooting EN | #4 conn_pool | `[observability/logging]` | `[observability/metrics]` | Intra-vocab misclassification |

## Observations (evidence collected at Phase 2b)

### 1. Genre-pair confusability predictions — first evidence

Pre-experiment prediction (recorded in `b2-v2-handoff.md`): the pairs
**ADR↔postmortem** (rationalization vocabulary) and **runbook↔
troubleshooting** (procedure vs symptom-driven procedure) are most
likely to confuse rankers.

Phase 2b evidence points:

- ko troubleshooting genre-primary query → postgres/runbook top-1
  (both postgres-only and cross-topic runs). `runbook.md` vacuum chunk
  shares `수동 실행`/`확인`/`점검` tokens with troubleshooting
  diagnostic vocabulary. **2/2 consistent misses — runbook↔
  troubleshooting pair confirmed once in ko/postgres.**

- No ADR↔postmortem confusion evidence yet; both accuracies 4/4 in
  both experiments. Continue watching in subsequent topics.

Phase 5 confusion matrix either confirms or refutes the pair-level
prediction; pre-registered so it stays a prediction, not a
post-hoc narrative.

### 2. Graded secondary presence — first observation

Batch 5 adr KO #4 (Logical Replication ADR) had two body-supported
secondary candidates at noticeably different strength:

- **Strong presence**: "복제 지연 가능성을 감수" — replication lag is
  a core consequence of the decision, warranting
  `observability/metrics` (the measurement surface for lag).
- **Weak presence**: "정합성 이슈가 발생하면 재검토" — consistency
  issues appear only as a re-evaluation trigger, a brief mention at
  the end. Would warrant `data_pipelines/quality` but only weakly.

Current relevance model is binary (`primary=1.0`, `secondary=0.5`).
This observation suggests **graded secondary** (e.g. 1.0 / 0.7 / 0.4 /
0) may surface a discriminative signal that binary flattens. Not
proposing to implement now; recording as an Option-2 candidate for
Phase 5 calibration.

### 3. Topic boundary — KO troubleshooting anchor crosses topics

In the cross-topic experiment (64 chunks), the strengthened postgres
troubleshooting query `pg_stat_replication bloat 증상 의심 점검 진단`
returned `caching/troubleshooting` top-1 under both BM25 and dense.

Interpretation: the troubleshooting anchor vocabulary
(`증상`/`의심`/`점검`/`세요` family) is **topic-agnostic** — it binds
to the troubleshooting genre regardless of topic vocabulary. This is
positive evidence that genre anchors *exist* in the corpus; they just
lose to stronger topic signal in topic-strong topics like postgres.

Bleed rate overall: 1/16 = 6.3% (below the B-1 override threshold of
"medium+" — see `b2-v2-handoff.md`'s locked scenario preference).

## Deferred decisions (Phase 3b / Phase 5 / Option 2 backlog)

- [ ] **Drift validator matrix (Phase 3b infra)** — three-tier rule
  set derived from accumulated curation ledger:
  - *Forbidden pairs* (auto-reject): `postgres/* primary → search/*
    secondary`, similar cross-domain vocab mixing
  - *Manual-review pairs* (flag, not block): `postgres/* primary →
    k8s/networking secondary` and similar ambiguous adjacencies
  - *Allowed pairs* (explicit greenlist): `postgres/* primary →
    observability/metrics secondary` — the common legitimate links

  Do not implement until at least 5 topics are ledgered; earlier
  automation fixes rules based on a biased small sample.

- [ ] **Graded secondary relevance (Option 2 for Phase 5)** — if
  Phase 5 calibration shows binary secondary presence under-
  discriminates (e.g. floor sensitivity too coarse), extend to
  `{1.0, 0.7, 0.4, 0.0}` graded presence. Evaluation trigger:
  per-type nDCG variance > per-type MRR variance (binary secondary
  would flatten the former).

- [ ] **Genre confusion matrix (Phase 5)** — compute full
  {4 genres × 4 genres × 2 langs} = 32-cell confusion across the
  final corpus. Verify the pre-registered prediction that ADR↔
  postmortem and runbook↔troubleshooting dominate off-diagonal
  mass.

- [ ] **Curator over-correction rate tracking** — maintain the
  "Claude over-correction" category count across topics. If it
  grows past ~10% of total corrections, relax curation criteria
  (current check is "body-supported evidence for every secondary";
  may need to be "body-supported OR strongly topic-adjacent with
  explicit rationale").
