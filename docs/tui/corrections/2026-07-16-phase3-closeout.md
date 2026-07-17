# TUI Phase 3 Closeout

- Record ID: `2026-07-16-tui-phase3-closeout`
- Date: 2026-07-16 (Asia/Seoul)
- Origin: implementation of the user-approved Phase 3 runtime contracts
- Scope: shared TUI application/runtime/presentation infrastructure only
- Status: implemented and verified; no Phase 4 domain workflow exposed

## Baseline protection

This is a post-baseline implementation record. It does not rewrite the
original 2026-07-15 rebuild plan, the decision-gate audit, or any Phase 0-2
record. The approval source is
`docs/tui/amendments/2026-07-16-phase3-runtime-contracts.md`.

No memtomem memory entry was created, rewritten, or indexed during this phase.
No file under `memtomem.cli` and no console-script declaration changed.

## Delivered contracts

### Results, progress, cancellation, and operation ownership

- Framework-neutral contracts define queued/running plus the approved
  `Cancelling`, `Succeeded`, `Partial`, `Failed`, and `Cancelled` meanings.
- Structured warnings, errors, progress, mutation effects, safe parameters,
  exit policy, recovery action, and cancellation payloads do not depend on
  Click, Rich output, or Textual widgets.
- Cooperative cancellation can carry completed counts, retained writes,
  search-cache effects, and a resume action. It cannot accidentally carry a
  non-Cancelled terminal result.
- `OperationRunner` owns lazily created coroutine tasks independently of a
  screen, isolates listener failures, rejects conflicting mutation keys,
  shields domain work from an awaiting caller's cancellation, and applies
  WAIT/CANCEL/BLOCK exit policy.
- External app teardown has a separate force-close path so a BLOCK operation
  cannot leak after the driver has already unmounted. Terminal history is
  bounded while existing handles remain usable.
- No TASKS badge, panel, route, list, or Task Center workflow was added. F4
  remains contextual Details. The older dormant Phase 2 registry remains
  untouched for compatibility and is not used by the new runner.

### Runtime generations and DEV isolation

- `RuntimeManager` construction is side-effect free. The first component
  generation is created only when a feature requests a runtime lease.
- Concurrent first use coalesces into one bootstrap. Candidate reload failure
  leaves the active generation available; successful swap retires the old
  generation and closes it once every lease drains.
- All component resources are attempted during close even if an earlier close
  fails. Internal exceptions are retained for diagnostics while the shell
  shows only a user-safe close message. A close failure requires a second quit
  confirmation before final exit.
- DEV config, config.d, database, memory roots, and FastEmbed cache paths are
  contained by `<project>/.dev/.memtomem`. The FastEmbed override remains
  active for the entire lazy model lifetime and the previous process value is
  restored after close or failed initial bootstrap. Normal mode is unchanged.
- Gates 1-3 remain unresolved. The manager exposes validated reload/swap seams
  but does not persist config, rebuild FTS, or implement embedding-revert
  behavior.

### Approved Gate 6 cache behavior

- `SearchPipeline.invalidate_result_cache()` increments the result generation
  and clears only bounded search results. Existing `invalidate_cache()` keeps
  its broad result-plus-query-expansion behavior for current callers.
- Result-cache suspension is nestable and bypasses reads and writes without
  invalidating a warm cache by itself.
- `RuntimeManager.run_mutation()` is the standard composition seam for
  mutation serialization, runtime leasing, cache bypass, structured-result
  observation, and one-time invalidation.
- Current and still-leased retired runtime generations are protected and have
  their result caches suspended together. A confirmed search-visible change
  invalidates every such generation before reads/writes resume.
- Preview, dry-run, no-op, validation failure, and cancellation-before-write
  leave result and expansion caches intact. Partial or Cancelled results that
  retain completed writes invalidate result caches. Query expansion and model
  caches remain warm for data-only changes.

### Shared Textual presentation

- Reusable semantic families now cover form rows, panel/modal action bars,
  literal data tables, empty/error states, operation lifecycle states,
  consequence-first previews, fingerprint revalidation, and confirmation.
- Destructive Apply is disabled after a fingerprint mismatch. Optional typed
  confirmation requires an exact match; Enter in the input moves focus to
  Apply and never executes immediately. Cancel owns initial focus.
- The 32x8 floor keeps State Changed, Apply, and Cancel visible. Exact typed
  confirmation remains operable with both solid and ASCII terminal borders.
- Dynamic labels, values, paths, messages, fingerprints, and table cells are
  rendered literally. CSS uses shared semantic classes; no new control-ID
  selector was added.

## Stitch evidence and limits

- Project: `7602308868624266029`
- Corrected component reference:
  `f0d3003973ed4972a103d21e34673679`
- Session: `9670231578208116656`
- Design system: `assets/23f97e12bb24472da7a882da5bb694e4`

The implementation uses the corrected board only for hierarchy, component
families, consequence emphasis, and semantic state grouping. It does not copy
invented capabilities, TASKS surfaces, glow/blur effects, browser geometry, or
web-only interaction. Repository behavior and tested Textual output remain the
authority.

## Implementation files

New application/runtime modules:

- `packages/memtomem/src/memtomem/tui/application/contracts.py`
- `packages/memtomem/src/memtomem/tui/application/operations.py`
- `packages/memtomem/src/memtomem/tui/application/cache_policy.py`
- `packages/memtomem/src/memtomem/tui/application/runtime.py`

New shared presenters:

- `packages/memtomem/src/memtomem/tui/widgets/forms.py`
- `packages/memtomem/src/memtomem/tui/widgets/tables.py`
- `packages/memtomem/src/memtomem/tui/widgets/preview.py`
- `packages/memtomem/src/memtomem/tui/widgets/operation_status.py`

Modified production files:

- `packages/memtomem/src/memtomem/search/pipeline.py`
- `packages/memtomem/src/memtomem/tui/runtime.py`
- `packages/memtomem/src/memtomem/tui/screens/shell.py`
- `packages/memtomem/src/memtomem/tui/styles/layout.tcss`
- `packages/memtomem/src/memtomem/tui/styles/components.tcss`
- `packages/memtomem/src/memtomem/tui/styles/states.tcss`

New focused tests:

- `packages/memtomem/tests/test_search_cache_policy.py`
- `packages/memtomem/tests/test_tui_app_lifecycle.py`
- `packages/memtomem/tests/test_tui_application_contracts.py`
- `packages/memtomem/tests/test_tui_cache_policy.py`
- `packages/memtomem/tests/test_tui_operation_status_widget.py`
- `packages/memtomem/tests/test_tui_operations.py`
- `packages/memtomem/tests/test_tui_phase3_widgets.py`
- `packages/memtomem/tests/test_tui_runtime_cache_integration.py`
- `packages/memtomem/tests/test_tui_runtime_environment.py`
- `packages/memtomem/tests/test_tui_runtime_manager.py`

The DEV containment assertion in
`packages/memtomem/tests/test_tui_external_contracts.py` was extended.

## Verification

- Focused Phase 3 foundation run: `83 passed` before final audit fixes.
- Final operation/cache/minimum-viewport rerun: `30 passed`.
- Complete Phase 0-3 TUI suite with unraisable warnings promoted to errors:
  `191 passed`.
- Existing search pipeline, temporal validity, project-scope, and tag-service
  regression suite: `164 passed`.
- Ruff check: passed.
- Ruff format check: passed.
- Mypy (13 changed source files): passed.
- `tools/tui_parity_manifest.py --check`: passed.
- `git diff --check`: passed.
- Rendered SVGs at 32x8 confirmed visible Apply/Cancel labels and a visible
  typed-confirmation value; pilot tests also assert regions and interactions.

## Phase 4 boundary

Phase 3 deliberately exposes no real Home/Search mutation or TASKS surface.
Phase 4 may now build the representative Home/Status/Search vertical slice on
these contracts. It must keep Home/Status read-only under approved Gate 9 and
must not cross unresolved Gates 1-3.

## Rollback

1. Delete the four new application/runtime modules, four new presenter modules,
   and ten new focused test files listed above.
2. Revert only the Phase 3 edits in the six modified production files and the
   DEV assertion added to `test_tui_external_contracts.py`.
3. Delete the matching `2026-07-16-tui-phase3-runtime-contracts` amendment block
   from the ignored local `packages/memtomem/src/memtomem/tui/AGENTS.md`.
4. Remove the Phase 3 amendment and closeout links from `docs/tui/README.md`,
   then delete this closeout and
   `docs/tui/amendments/2026-07-16-phase3-runtime-contracts.md`.

No memory rollback is required because no memory was touched.
