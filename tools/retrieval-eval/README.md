# B.2 v2 retrieval evaluation tools

Portable measurement scripts backing the Phase 2 multilingual
regression methodology. Reproduces the numbers recorded in
`docs/planning/b2-v2-phase1-validation.md` §§ 8-11 and
`docs/planning/b2-v2-phase2b-ledger.md` § "Sensitivity spot-check
outcome".

**These tools ARE committed** (unlike `scripts/` which is gitignored
for local-only helpers per commit `2b601d3`). Reviewers and future
contributors must be able to reproduce the reported 0/8 divergence
numbers without access to a specific contributor's local setup.

## Tools

| File | Purpose |
|---|---|
| `measure_sensitivity.py` | Runs genre-primary divergence spot-check for one topic. Produces `X/N divergence + Y/N BM25 top-1 + Z/N dense top-1` output. |
| `compute_idf_baseline.py` | Pre-measurement IDF + body-overlap check for any new topic's queries. Enforces "overlap < 0.5" rule from phase1-validation § 11.5. |

## Workflow for each new topic

1. **Design queries** following the canonical pattern
   (`<topic-prefix> + <genre anchor vocabulary>`). See
   `measure_sensitivity.py:QUERIES` for postgres/cost_optimization
   references.
2. **Pre-measure** IDF + body overlap:
   ```bash
   uv run python tools/retrieval-eval/compute_idf_baseline.py
   ```
   Target ranges: KO mean tokens 5.7-7.8, idf_sum 12.67-17.14;
   EN mean tokens 6.4-8.6, idf_sum 12.04-16.28. Target body overlap
   < 0.5; flagged queries get a ledger note.
3. **Add queries** to `measure_sensitivity.py:QUERIES` dict.
4. **Run divergence**:
   ```bash
   PYTHONHASHSEED=0 OMP_NUM_THREADS=1 uv run python \
       tools/retrieval-eval/measure_sensitivity.py --topic <topic_name>
   ```
5. **Determinism check**: repeat step 4. Output must be byte-identical
   across runs. If not, investigate (fastembed cache,
   `PYTHONHASHSEED`, ONNX threads) before trusting the numbers.
6. **Record result** in `phase2b-ledger.md` curation section for that
   topic + `phase1-validation.md` new subsection (§ 11 = cost_opt
   precedent, § 12+ for future topics).

## Reference: Phase 2 canonical results

All measurements below are reproducible via:
```bash
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 uv run python \
    tools/retrieval-eval/measure_sensitivity.py --topic <topic_name>
```

| Topic | Divergence | BM25 top-1 | Dense top-1 | Recorded in |
|---|---|---|---|---|
| postgres | **0/8** | 7/8 | 7/8 | phase1-validation § 10.2 |
| cost_optimization | **0/8** | 6/8 | 6/8 | phase1-validation § 11.2 |

Both deterministic across 2 consecutive runs. Numbers above are the
methodology anchor — if a future run produces different numbers, the
environment has drifted (fastembed version, ONNX model cache, corpus
fixtures, or seed handling) and the gap needs investigation before
new topic measurements are trusted.

## Invariants

- **Divergence definition frozen** (see
  `phase2b-ledger.md` § "Formal definitions"): top-3 chunk IDs under
  `rrf_weights=[1.0, 0.0]` vs `[0.0, 1.0]`, exact ordered list
  equality. Post-hoc redefinition prohibited.
- **Simple queries are the canonical comparison set.** Strengthened
  variants (proper-noun-rich) are contingent reserves, only activated
  if a topic's simple-query result is methodologically surprising.
  Don't mix-and-match across topics.
- **Body overlap pre-check is mandatory** before a new topic's
  divergence is reported. Results for queries with overlap ≥ 0.5
  are labeled "measurement-consistent but signal-confounded" in the
  ledger; not silently reported as clean divergence readings.

## Why `tools/`, not `scripts/`?

`scripts/` is gitignored (`.gitignore` line 48, commit `2b601d3`
rationale: "local QA automation... not portable across clones"). The
measurement scripts in this directory ARE portable (plain `uv run
python`, committed fixtures, no contributor-specific Claude Code
setup dependency), so they belong in a committed location.

`tools/` is the new home for portable research/methodology artifacts.
If future IR benchmarks get richer (latency, model comparisons,
etc.), `tools/ir-benchmarks/` may split off; this directory stays
focused on the Phase 2 sensitivity methodology.
