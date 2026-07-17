# TUI Phase 3 Runtime Contracts Amendment

Amendment ID: `2026-07-16-tui-phase3-runtime-contracts`

- Approved: 2026-07-16 (Asia/Seoul)
- Origin: explicit user decisions during the TUI Phase 3 entry review
- Scope: TUI application/runtime infrastructure only; no CLI behavior, source,
  output, or script-entry change
- Status: approved for implementation

## Baseline protection

This is a post-baseline artifact. It does not rewrite the original 2026-07-15
TUI rebuild plan, the original decision-gate audit, or the Phase 2 records.

- `packages/memtomem/src/memtomem/tui/AGENTS.md` pre-amendment SHA-256:
  `516ab3f8d6d6433562ec7f8d8c8943f3e8213c3095d2096a63ed69d2c6d5fb3a`
- `docs/tui/decision-gates.md` untouched baseline SHA-256:
  `026c39f009aba9870568ad6069ce94670a7241b388644339671a9f81fb838e44`
- `docs/tui/amendments/2026-07-16-task-center-visibility.md` superseded
  baseline SHA-256:
  `fcd11899d6635374776176c58bfd35a945a9d47fe0c3bf1815b2bf14e175f0fb`

The decision-gate document intentionally retains its original
`pending-user-decision` snapshot. This amendment is the separate authorization
record for Gate 6. Gates 1-3 remain unresolved, so Phase 3 may establish a
runtime API but must not implement their configuration side effects.

## Approved operation-result contract

- `Succeeded` is terminal: every required unit completed without a domain
  failure.
- `Partial` is terminal: the operation reached normal completion, but only
  part of its requested work succeeded. It must report completed, failed,
  skipped, remaining, warnings, and recovery information as applicable.
- `Failed` is terminal: the requested operation did not produce a successful
  domain outcome. A user-safe error code/message must be available without
  leaking secrets or formatted CLI output.
- `Cancelling` is an intermediate state after cancellation is requested and
  before the operation acknowledges a cooperative stopping point.
- `Cancelled` is terminal after that acknowledgement. Completed writes are
  not relabelled as `Partial` or rolled back merely because later units were
  cancelled; the result must preserve completed/remaining counts and a resume
  path. Any completed mutation is still treated as a data change for cache
  policy.

Cancellation is cooperative. The application owns the coroutine lifetime,
and navigation, resize, or originating-screen unmount must not cancel a domain
operation.

## Approved TASKS boundary

- Do not develop or expose a TASKS badge, page, panel, route, list, or Task
  Center workflow in Phase 3 or the remaining rebuild phases unless the user
  later makes a new explicit product decision.
- F4 remains the contextual Details panel.
- Existing dormant Phase 2 task-registry code may remain for compatibility,
  but new domain work must not depend on a user-visible Task Center.
- Retain only the non-visual application infrastructure required for safe real
  work: coroutine ownership, progress events, cooperative cancellation,
  conflicting-mutation exclusion, and orderly application shutdown. This
  internal operation coordinator is not a Task Center feature.

This supersedes the earlier amendment's suggestion that persistent task status
might automatically return once domain work is connected. Reintroduction now
always requires a separate explicit decision.

## Approved Gate 6 cache policy

The TUI's persistent runtime uses two distinct cache policies:

1. Search-result cache
   - During a mutation's critical window, bypass result-cache reads and writes
     so stale entries cannot be served or repopulated.
   - If the final structured mutation effect reports any search-visible data
     change, including a partial or cancelled operation that already wrote
     data, increment the result-cache generation and clear the entire
     search-result cache before ending the bypass window.
   - If preview, dry-run, no-op, validation failure, failure before the first
     write, or cancellation before the first write changes no data, leave the
     cache and its generation untouched.
2. Expansion and model caches
   - A data-only mutation must retain the LLM query-expansion cache and
     provider/model disk caches.
   - A configuration or runtime-generation change that can alter query
     interpretation may use the existing broad invalidation path. Implementing
     those configuration side effects remains blocked on Gates 1-3.

Whole result-cache invalidation is preferred over selective dependency
tracking because additions and semantic/BM25 content changes may affect any
query, while the current bounded cache is small. The existing TTL remains a
freshness limit, not a simulated hardware-cache allocation. Do not reserve a
fixed physical-memory pool. A measured byte-budgeted LRU may be considered
later only if telemetry shows memory pressure.

## Stitch evidence boundary

- Project: `7602308868624266029`
- Corrected Phase 3 component-reference screen:
  `f0d3003973ed4972a103d21e34673679`
- Generation session: `9670231578208116656`
- Design system: `assets/23f97e12bb24472da7a882da5bb694e4`

Use that screen only for feasible terminal hierarchy, semantic state families,
form/table composition, and Preview/Confirm emphasis. Repository contracts,
actual memtomem capabilities, and Textual rendering constraints are
authoritative. Do not implement invented Stitch functions, web-only effects,
per-component-ID styling, or a TASKS surface.

## Acceptance checks

- Typed contracts distinguish all five approved result/lifecycle states and
  preserve mutation effects on partial/cancelled outcomes.
- The internal operation coordinator owns tasks, supports cooperative cancel,
  isolates listeners, rejects conflicting mutations, and drains/cancels or
  blocks exit according to an explicit policy.
- Runtime generations swap atomically; a failed candidate leaves the active
  generation usable, and retired generations close once outstanding leases
  drain.
- Dev-mode component bootstrap and model caches remain under the resolved dev
  state root; normal-mode paths and the CLI remain unchanged.
- Result-cache-only invalidation, mutation bypass, no-change retention, and
  in-flight version protection have focused tests.
- Common forms, tables, Preview/Confirm, errors, and result states use reusable
  semantic classes and render at the documented viewport floors.
- No TASKS UI appears, and F4 remains Details.
- `tools/tui_parity_manifest.py --check` proves the CLI baseline is unchanged.

## Rollback

1. Revert only the Phase 3 implementation files named in the Phase 3 closeout
   record; do not alter CLI files or earlier Phase 2 artifacts.
2. Delete the matching
   `POST-BASELINE AMENDMENT BEGIN` / `POST-BASELINE AMENDMENT END` block from
   `packages/memtomem/src/memtomem/tui/AGENTS.md`.
3. Remove this artifact's entry from `docs/tui/README.md`.
4. Delete this artifact.

Those steps restore the pre-Phase 3 plan and decision records byte-for-byte.
