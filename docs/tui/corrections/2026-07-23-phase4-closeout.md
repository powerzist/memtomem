# TUI Phase 4 Closeout

- Record ID: `2026-07-23-tui-phase4-closeout`
- Date: 2026-07-23 (Asia/Seoul)
- Origin: implementation and final audit of the user-approved Phase 4 scope
- Scope: Home/Status and Search representative vertical slice only
- Status: implemented and verified; Phase 5 work has not started

## Baseline protection

This is a separate post-baseline implementation record. It does not rewrite
the original 2026-07-15 rebuild plan, its decision-gate audit, or any earlier
phase record. The rollback-safe Phase 12 Search-cancellation and
Search-result-editor amendments in the local TUI handoff plan also remain
unchanged.

No memtomem memory entry was created, rewritten, or indexed during this
closeout. No file under `memtomem.cli`, no Click declaration, and no
console-script entry changed.

## Approved Phase 4 product contract

- Home/Status is strictly read-only. It must not create a directory or
  database, migrate config or schema, acquire a runtime lease, start a
  watcher, index files, or generate embeddings.
- Search uses the real non-CLI search runtime and preserves the fixed pipeline
  behavior, side effects, partial failures, filters, and result meaning.
- Search discloses storage initialization and migration before the first
  runtime lease. It never auto-indexes files or builds missing document
  embeddings.
- The initial Top K value comes from the effective
  `search.default_top_k` setting. A user override receives integer conversion
  only; Phase 4 adds no TUI-specific numeric range.
- Search results use a native Main table and F4 Details. CLI
  `table/json/plain/context/smart` presentation formats are not exposed as a
  TUI selector.
- Reranker degradation is visible as a structured warning while usable
  pre-rerank results remain available.
- Search remains explicitly non-cancellable and exposes no cancel control.
  Analysis, feasibility proof, and implementation remain assigned to Phase 12.
- TASKS and Task Center remain unexposed. F4 remains contextual Details.

## Delivered Home/Status behavior

- `ReadOnlyDiagnosticsService` reads config and SQLite state through explicit
  no-migration paths and SQLite read-only/query-only mode.
- Structured states distinguish missing setup, missing or unreadable
  database, migration-required schema, and ready schema.
- The surface reports config/storage paths, storage backend, schema
  differences, chunk/source/orphan counts, dense-vector coverage, embedding
  compatibility, effective default Top K, RRF k, tokenizer, scheduler, and
  watchdog state.
- Independent diagnostic problems retain every fact that is still available
  and present user-safe warnings without exposing internal secrets.
- Malformed JSON and structurally invalid known config data block readiness
  instead of being silently replaced with defaults. The default tolerant
  behavior of non-TUI config callers remains unchanged.

## Delivered Search behavior

- `SearchService` owns typed preflight, request, response, result, context,
  statistics, warning, and error boundaries independently of Click and CLI
  output.
- Preflight reads the effective default Top K without mutation and reports the
  exact initialization/migration transition. Execution revalidates config
  before acquiring a runtime lease.
- Query, Top K, source, tag, namespace, scope, and as-of inputs reach the real
  search pipeline with the established CLI validation meaning.
- Successful empty results, empty-index failure, total retrieval failure,
  BM25/dense degradation, missing dense coverage, embedding problems, and
  reranker degradation remain distinguishable.
- Result rows are a scan-friendly projection. Details preserves full literal
  content, metadata, expanded context, and retrieval statistics.
- Provider-specific diagnostic rerank outcomes are per call rather than
  shared mutable state, so concurrent searches cannot leak degradation state.
  Existing direct reranker call behavior remains compatible.

## Presentation and interaction

- Home and Memories are persistent route surfaces inside the modular shell;
  switching routes or responsive modes preserves the Search form, results,
  selection, and Details state.
- Wide, standard, compact, and extreme layouts reuse semantic TCSS families
  for route surfaces, filter grids, status rows, notices, operation states,
  tables, literal content, and action bars. Phase 4 added no feature-control
  ID selector family.
- Keyboard, mouse, focus restoration, F4 Details, route switching, ASCII
  borders, resize, literal rendering, partial results, safe failures, and
  non-cancellable lifecycle are covered by rendered Textual pilot tests.
- A generation guard discards stale post-refresh reveal callbacks so an older
  operation-state scroll cannot hide the final warning or error on compact
  screens.

## Stitch evidence and limits

- Project: `7602308868624266029`
- Design system: `assets/23f97e12bb24472da7a882da5bb694e4`
- Design system name: `Operational Terminal Logic`
- Phase 4 final board: `1dff225f528a4f648a60c2d8aef9c7e6`
- Phase 4 Textual reference board: `1d21fdc38446467f80afa58ba9bfc057`
- Wide Search reference: `53b647e4b2d84ab5bd8a5296a08a9a07`
- Compact Search reference: `5fb650a4a76d4b3eb167f6c29a599286`
- Safe-floor reference: `0e6873a87b084aecbe95220525e1df5b`
- Extreme-small reference: `57ab00155d4c47efabfee19e61203cce`

The implementation uses these references for density, hierarchy, responsive
disclosure, table/detail separation, semantic state language, and terminal
focus emphasis. It does not copy browser geometry, web fonts, hover-only
interaction, invented functions, or a TASKS surface. The local Textual
contracts and rendered tests remain authoritative.

## Implementation files

New Phase 4 production modules:

- `packages/memtomem/src/memtomem/tui/application/diagnostics.py`
- `packages/memtomem/src/memtomem/tui/application/search.py`
- `packages/memtomem/src/memtomem/tui/screens/home.py`
- `packages/memtomem/src/memtomem/tui/screens/memories.py`

Modified production files:

- `packages/memtomem/src/memtomem/config.py`
- `packages/memtomem/src/memtomem/search/pipeline.py`
- `packages/memtomem/src/memtomem/search/reranker/base.py`
- `packages/memtomem/src/memtomem/search/reranker/cohere.py`
- `packages/memtomem/src/memtomem/search/reranker/fastembed.py`
- `packages/memtomem/src/memtomem/search/reranker/local.py`
- `packages/memtomem/src/memtomem/tui/runtime.py`
- `packages/memtomem/src/memtomem/tui/screens/shell.py`
- `packages/memtomem/src/memtomem/tui/state.py`
- `packages/memtomem/src/memtomem/tui/styles/components.tcss`
- `packages/memtomem/src/memtomem/tui/styles/layout.tcss`
- `packages/memtomem/src/memtomem/tui/styles/responsive.tcss`
- `packages/memtomem/src/memtomem/tui/styles/states.tcss`
- `packages/memtomem/src/memtomem/tui/widgets/operation_status.py`
- `packages/memtomem/src/memtomem/tui/widgets/preview.py`
- `packages/memtomem/src/memtomem/tui/widgets/tables.py`

New Phase 4 tests:

- `packages/memtomem/tests/test_tui_phase4_characterization.py`
- `packages/memtomem/tests/test_tui_phase4_interactions.py`
- `packages/memtomem/tests/test_tui_phase4_widgets.py`
- `packages/memtomem/tests/test_tui_readonly_diagnostics.py`
- `packages/memtomem/tests/test_tui_search_service.py`

Search, reranker, launcher, and external-contract regressions were extended in:

- `packages/memtomem/tests/test_pipeline.py`
- `packages/memtomem/tests/test_reranker.py`
- `packages/memtomem/tests/test_tui_cli.py`
- `packages/memtomem/tests/test_tui_external_contracts.py`

The native Search and Status dispositions and evidence were recorded in
`docs/tui/parity-manifest.json`.

## Verification

- Final read-only diagnostics and Search service run: `32 passed`.
- Final config compatibility, pipeline, and reranker run: `114 passed`.
- Complete TUI suite with unraisable warnings promoted to errors:
  `243 passed`.
- The rendered suite composes Home and Search at `160x50`, `120x30`,
  `100x24`, `99x24`, `80x20`, `60x16`, `48x12`, `40x10`, and `32x8`;
  it asserts terminal bounds and visible route/error/warning text.
- Ruff check for all memtomem source and every changed Phase 4 test: passed.
- Ruff format check: `302 files already formatted`.
- Mypy for all 16 changed Phase 4 Python source files: passed.
- `tools/tui_parity_manifest.py --check`: passed.
- `git diff --check`: passed.
- CLI source diff: empty.

The advisory full-source mypy run is not green: it reports 45 pre-existing
errors in six observability, Web, and CLI files outside this change. An earlier
full non-Ollama repository run produced `6304 passed`, `304 skipped`,
`46 deselected`, and `15 failed`. The one TUI/ADR guard failure from that run
was fixed by using `all_index_roots()` and is covered by the final 243-pass TUI
suite. The other 14 observed failures were unrelated Windows symlink/path,
CRLF, and privacy-performance cases; they were not altered or hidden, and the
16-minute full suite was not rerun after the isolated TUI correction.

## Phase 5 boundary

Phase 4 is complete, but this record does not authorize Phase 5
implementation. Phase 5 must begin with its own entry review and explicit
approval. It covers the remaining Memories and setup workflows: Add, Recall,
Read/List, Ask/shell behavior, Init, Config, and Settings.

Before Phase 5 code depends on an unresolved behavior, the corresponding
decision gate must be characterized and approved. In particular, setup and
configuration work must not silently decide tokenizer/FTS rebuild behavior,
`config.d` save/merge behavior, embedding-revert behavior, streaming-root
containment, or non-atomic Add behavior.

## Rollback

1. Delete the four new Phase 4 production modules and five new Phase 4 test
   files listed above.
2. Revert only the Phase 4 hunks in the sixteen modified production files and
   four extended regression files listed above.
3. Revert only the Search and Status audit rows in
   `docs/tui/parity-manifest.json`.
4. Remove the Phase 4 closeout paragraph from `docs/tui/README.md`, then delete
   this file.

The original rebuild plan, its Phase 12 amendments, and memtomem memory were
not changed by this closeout, so they require no rollback.
