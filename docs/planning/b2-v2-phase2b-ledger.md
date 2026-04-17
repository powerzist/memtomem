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

## Curation ledger — Phase 2c cost_optimization (0 drift corrections / 32 chunks)

Drift rate 0/32 = 0%, an unexpected departure from the ~30% baseline
across Phase 1 (caching ko), 2a (caching en), and 2b (postgres). The
result is surprising but not post-hoc rationalized: hypotheses below
are pre-registered before the security-topic run, and
ruling-discrimination rules are locked. See "Security drift
pre-registration" subsection below.

### Category comparison (postgres 2b vs cost_opt 2c)

| Category | postgres 2b | cost_opt 2c |
|---|---|---|
| Out-of-vocab expansion | 1 | 0 |
| Intra-vocab misclassification | 4 | 0 |
| Absent-topic projection | 3 | 0 |
| Claude over-correction | 1 | 0 |
| **Total** | **9/32 (28%)** | **0/32 (0%)** |

The per-category breakdown matters more than the headline rate. H1
(structural cleanliness) only prevents the "intra-vocab
misclassification" row. H2 (prompt refinement with Phase 2b-derived
drift-to-avoid block) can prevent "intra-vocab" AND "absent-topic
projection" AND "out-of-vocab" — three rows. The fact that cost_opt
shows 0 across all four categories is asymmetric evidence for H2 —
but a single topic is not sufficient to discriminate. Security is
the discriminating test.

### Hypotheses (pre-registered, discrimination at security)

- **H1 (structural cleanliness dominant)**: cost_optimization
  subtopics (compute/storage/network/database/observability) map 1:1
  to AWS service categories, giving cleaner semantic boundaries than
  postgres's overlapping subtopics (indexing↔vacuum↔partitioning).
  Mechanism: reduces intra-vocab misclassification. Independent of
  absent-topic projection.
- **H2 (prompt refinement dominant)**: the Phase 2b-derived "Drift
  to avoid" block with 5 cost_opt-specific confusion examples acted
  as a prefilter. Mechanism: addresses intra-vocab AND
  absent-projection AND out-of-vocab simultaneously. Transferable
  across topics.
- **H3 (mixed, unequal weights)**: both H1 and H2 contribute; neither
  dominates.
- **H_null (pure chance)**: ruled out. Binomial P(0 drift | p=0.28,
  n=32) = 1.2e-5.

### Boundary-case principles (established Phase 3a cost_opt review)

**Principle 1 (Tool-function cluster rule)**

Body need not mention subtopic X literally if it mentions a
widely-recognized alternative or derivative Y of X, where the Y→X
relationship is explicitly documented in standard technical
references.

Verification protocol:
- *Primary source*: the tool/concept's own official documentation
  (README, docs site, RFC, spec)
- *Acceptable secondary source*: project wiki section titled as
  comparison/alternative to subtopic X
- *Not acceptable*: blog posts, Stack Overflow answers, AI-generated
  summaries, general "category" groupings (e.g., "both are caching
  tools" is insufficient)
- **Curator MUST cite the source in the ledger when invoking
  Principle 1.** Ledger entries without citation are invalid
  regardless of stated judgment. Citation-less invocations are the
  loophole; citation requirement is the bound.

Qualifying example: pg_repack → postgres/vacuum. pg_repack README
first line: "pg_repack is a PostgreSQL extension which lets you
remove bloat from tables and indexes... Unlike CLUSTER and VACUUM
FULL it works online." Self-documented as VACUUM FULL alternative.

Non-qualifying example: "DNS server" → networking/service_mesh.
General association only; service mesh specs do not list DNS as a
core primitive.

**Principle 2 (Functional split rule)**

When body describes problem-side and fix-side components separately,
both may be tagged as secondary even within the same parent topic
(e.g., `networking/load_balancing` + `networking/dns`). Body support
required for each side.

**Principle 3 (Same-topic secondary cap)**

At most 1 secondary may share the primary's topic. Body support
required. Example: primary = `cost_optimization/database`, secondary
may include one additional `cost_optimization/*` but not more.
Exceeding the cap is intra-topic over-tagging and dilutes the
"adjacent topic" signal that secondary is supposed to carry.

### Per-chunk boundary cases (cost_opt Phase 2c, 0 net corrections, 3 documented resolutions)

| Batch | Chunk | Primary | Secondary as submitted | Decision | Principle applied |
|---|---|---|---|---|---|
| runbook EN | #2 | cost_opt/storage | `[postgres/vacuum]` | kept | P1 (pg_repack cited above; VACUUM FULL alternative per project README) |
| troubleshooting KO | #3 | cost_opt/network | `[networking/load_balancing]` | **expanded** to `[networking/load_balancing, networking/dns]` | P2 (problem-side public ALB + fix-side CoreDNS both body-supported) |
| postmortem EN | #3 | cost_opt/database | `[postgres/partitioning, cost_optimization/storage]` | kept | P3 (1 intra-topic secondary within cap; gp3 volumes + pg_partman both body-supported; RDS spend line and EBS spend line are distinct AWS billing categories) |

### Subtopic freeze declaration (2026-04-17)

Corpus at 96 chunks (caching 32 + postgres 32 + cost_opt 32).
Subtopic list is locked: 15 topics × 5 subtopics = 75. No new
subtopics emerged during cost_opt generation; closed vocabulary
proved sufficient.

**Post-freeze amendment protocol**:
- If a chunk cannot be mapped to any existing subtopic, route to
  nearest closest entry and log in ledger as "unresolved gap".
- When unresolved-gap entries accumulate ≥ 3 distinct cases (same
  conceptual gap across ≥ 3 topics), trigger deliberate vocabulary
  expansion review — documented amendment with rationale, not
  emergency addition.
- Silent vocabulary expansion is the failure mode to prevent.

3-case threshold rationale: "1 case = individual judgment, 3 cases =
pattern." Arbitrary but explicit; prevents drift-by-accretion.

### Sensitivity spot-check outcome (measured 2026-04-17)

Measurement script: `/tmp/phase2c_cost_opt_sensitivity.py` (1:1 mirror of
`/tmp/phase2b_postgres_sensitivity.py`, only topic name + query prefix
changed). Determinism verified: 2 consecutive runs byte-identical.
Methodology anchor re-verified same session — postgres script
reproduced 0/8 divergence + 7/8 BM25 + 7/8 dense, confirming
environment stability.

**Results**: divergence 0/8 (0/4 KO, 0/4 EN), BM25 top-1 6/8, dense
top-1 6/8.

**Pre-registered outcome ruling**: counter-prediction realized.
cost_optimization reclassifies **topic-strong** (not topic-weak as
initially predicted). Full analysis in
`b2-v2-phase1-validation.md` § 11.

Key finding: the subtopic-vocabulary-density hypothesis
(`b2-v2-design.md` § "Topic-strong vs topic-weak") is **falsified**.
Both postgres (proper-noun-dense) and cost_optimization
(conceptually oriented) show identical 0/8 divergence. Revised
hypothesis: chunk-level artifact density dominates topic-level
vocabulary density — every chunk in both topics contains 2+
distinctive artifacts (commands, config keys, proper nouns) that
anchor BM25 and dense to the same chunk regardless of
`rrf_weights`. Security result will further discriminate; kafka
boundary case becomes less informative than originally designed
since the "proper-noun-heavy" distinction matters less.

### Formal definitions (Phase 2b-established, fixed across 14 topics)

**Divergence**:
```
For query q in language L against corpus C:
  top3_bm25(q)  = ordered top-3 chunk IDs with rrf_weights=(1.0, 0.0)
  top3_dense(q) = ordered top-3 chunk IDs with rrf_weights=(0.0, 1.0)
  diverge(q)    = 1 if top3_bm25(q) != top3_dense(q) else 0

Divergence rate per language = Σ diverge(q) / N_queries_per_lang
Aggregate reported as "X/N KO, Y/N EN" or combined "Z/2N total".
```

Post-hoc redefinition prohibited (e.g. "top-5 instead", "top-1 only",
"set equality instead of ordered list"). All 14 topics use this exact
definition.

**Drift** (curation-side):
```
For topic T, Phase 3a curator processes Gemini output with:
  N_chunks   = total chunks reviewed (8 batches × 4 = 32)
  N_drift    = count of chunks requiring a secondary-subtopic correction
  Categories = {out-of-vocab expansion, intra-vocab misclassification,
                absent-topic projection, Claude over-correction}

Drift rate per topic = N_drift / N_chunks
Reported as "N/32 (P%)" plus category distribution table.
```

Boundary cases resolved via Principles 1-3 (this section above) are
NOT counted as drift — they are documented as "decisions per
established principles" with the principle cited.

### Security pre-registration — drift × divergence (updated 2026-04-17)

Before security Gemini run. Two independent measurements, jointly
interpreted. Bucket boundaries locked; no post-hoc redefinition.

**Drift prediction** (Gemini output vs closed vocab, Phase 3a):

| Hypothesis | Drift range | Interpretation |
|---|---|---|
| H1 (structural cleanliness dominant) | 10-20% | Structure explains drift prevention; cost_opt was a special case. Prompt refinement contributes weakly. |
| H2 (prompt refinement dominant) | 0-5% | Prompt refinement explains most gain; transferable across topics regardless of subtopic geometry. |
| H3 (mixed, unequal weights) | 5-10% | Both factors contribute; neither dominates. |

**Divergence prediction** (BM25 vs dense top-3 agreement, Phase 2c
sensitivity spot-check):

| Hypothesis | Divergence range | Interpretation |
|---|---|---|
| D1 (topic-strong consistent) | 0-1/8 | Security joins postgres + cost_opt topic-strong cluster. Chunk-level artifact candidate gains first support (n=3). |
| D2 (genre signal emerges, moderate) | 3-5/8 | Security chunks have less distinctive artifacts than postgres/cost_opt; genre anchors start to separate BM25 from dense. |
| D3 (genre signal dominates, strong) | 6-8/8 | Genre anchors fully emerge; security chunks lack chunk-level artifact anchors. Chunk-level hypothesis falsified if paired with H2 (prompt-healthy). |
| (D2 fallback: 2/8) | 2/8 | Boundary between D1 and D2; inconclusive, requires kafka for discrimination. |

**Joint H × D interpretation matrix**:

```
              H1 (structural)    H2 (prompt)       H3 (mixed)
           ┌──────────────────┬──────────────────┬──────────────────┐
       D1  │ structural + all │ prompt + all     │ mixed + all      │
           │ topic-strong     │ topic-strong     │ topic-strong     │
           │ (universal)      │ (universal)      │ (universal)      │
           ├──────────────────┼──────────────────┼──────────────────┤
      D2/3 │ structural +     │ PROMPT + GENRE   │ mixed + genre    │
           │ genre emerges    │ EMERGES          │ emerges          │
           │                  │ ← best for       │                  │
           │                  │ chunk-artifact   │                  │
           │                  │ FALSIFICATION    │                  │
           └──────────────────┴──────────────────┴──────────────────┘
```

Cells of interest:
- **(H2, D2/D3)**: prompt hypothesis + genre emergence is the **best
  discriminating outcome** for the chunk-level artifact candidate
  (see `b2-v2-phase1-validation.md` § 11.4). Prompt quality high
  but divergence ≥ 4/8 → chunk artifacts are NOT the dominant
  mechanism → candidate falsified.
- **(H1, D1)**: structural dominance + universal topic-strong =
  chunk-level artifact candidate retained (but H1 weighted
  heavily).
- **(H2, D1)**: prompt dominant + universal topic-strong =
  strongest candidate support; prompt quality + chunk artifacts
  both contribute to invariance.

**If H3 realized** (drift 5-10%), next discriminator = kafka per
original cadence. Recorded outcome rules:
- Kafka drift < 3%: H2 gains weight (cost_opt + kafka both low
  despite structural differences).
- Kafka drift > 10%: H1 gains weight (cost_opt was the outlier;
  structure matters).
- Kafka also 5-10%: H3 confirmed as stable baseline. Update
  methodology: accept 5-10% as expected rate, factor into Phase 5
  threshold calibration.

### Kafka cadence contingency (added 2026-04-17 post-cost_opt)

Original cadence positioned kafka as "boundary between proper-noun-
heavy (like postgres) and conceptual (like caching)" to maximize
information gain from the topic-strong/weak axis.

Cost_opt counter-prediction outcome **reduces kafka's information
value**: cost_opt (conceptual) already shows topic-strong, so kafka
(proper-noun-heavy + conceptual mix) is very likely to also be
topic-strong. Kafka shifts from "boundary test" to
"redundant-confirmation test".

**Contingency (security-contingent)**:
- If security also shows 0-2/8 divergence (joining topic-strong
  cluster): kafka's information value ≈ confirmation only. Consider
  replacing kafka with a candidate **alternative boundary topic**:
  - **observability**: genres map naturally to distinct activities
    (runbook = dashboard/query setup, postmortem = incident
    narrative, adr = tool selection, troubleshooting = alert
    fatigue) — potentially shows genre signal emerging.
  - **security** (if it already ran as topic-weak): kafka becomes
    strongest topic-strong confirmation; retain.
- If security shows 3-8/8 divergence: security IS the topic-weak
  data point. Kafka retains original boundary role.

**Do not swap kafka before security result** — sunk-cost bias
avoidance. Record both paths here so post-security decision is
informed, not ad-hoc.

## Observations (evidence collected at Phase 2c)

### 1. No intra-topic drift despite cross-topic vocabulary pull

Chunks discussing NAT Gateway costs frequently reference
`networking/*` subtopics (load_balancing, dns) as secondaries.
Chunks discussing RDS costs frequently reference `postgres/*`
(vacuum, connection_pool, partitioning). Neither pattern produced
drift — Gemini correctly placed primary in `cost_optimization/*`
and secondaries in the adjacent topic.

Possible reason: cost_optimization subtopics are about SPEND;
adjacent subtopics are about MECHANICS. The two roles don't collide
because they answer different questions ("how much does this cost?"
vs "how does this work?").

Predicts: topics whose subtopics are about the same axis (e.g.,
postgres/indexing and postgres/vacuum both about maintenance ops)
will show higher intra-topic drift than cost_optimization.

### 2. First legitimate intra-topic secondary (→ Principle 3)

Batch 8 #3 (postmortem EN, `cost_optimization/database` primary,
`cost_optimization/storage` secondary alongside
`postgres/partitioning`) is the first v2-corpus chunk with an
intra-topic secondary. Cause: AWS billing structure (RDS spend line
and EBS-under-RDS spend line are distinct). Principle 3 was
established specifically for this case. Track whether other topics
produce analogous patterns — if they don't, Principle 3 remains
used-once.

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
  explicit rationale"). Phase 2c: 0 over-corrections (and 0 total
  corrections). If security is also low-drift, revisit whether
  the current criterion needs adjustment at all.

- [ ] **Principle 1 source-citation audit** — after 3 more topics,
  review ledger to verify every Principle 1 invocation cites a valid
  source per the verification protocol. If unverifiable invocations
  accumulate, tighten the protocol further (e.g., require explicit
  quote from the source rather than just a reference).
