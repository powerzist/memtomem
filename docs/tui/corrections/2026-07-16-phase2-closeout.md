# Phase 2 Closeout Correction Record

Record ID: `2026-07-16-phase2-closeout`

- Applied: 2026-07-16 (Asia/Seoul)
- Origin: user-approved work to reach the Phase 3 entry boundary
- Scope: Phase 2 TUI corrections and verification only
- Status: Phase 3 entry ready; no Phase 3 runtime or workflow was implemented

## Baseline protection

This is a separate post-baseline artifact. The original
`docs/tui/phase2-modular-shell.md` remains unchanged at SHA-256
`9275485d5572a513ba23976447aefe48efe9d6230639982e7c5f087b10b0a6fe`.
The root `AGENTS.md` rollback policy and the existing product-contract
amendments were not rewritten.

This record follows and does not replace
`2026-07-16-phase2-shell-defects.md`.

## Final Phase 2 corrections

### Textual-owned mouse lifecycle

The shell previously wrote only the `1000` and `1006` terminal sequences and
kept a second Boolean outside Textual's driver. Modes `1003` and `1015` could
remain active, and enabling mouse input after `--no-mouse` did not arm
Textual's shutdown cleanup.

`tui/mouse.py` now isolates the unavoidable private Textual driver boundary.
The active driver's `_mouse` flag is the single runtime state source, native
enable/disable helpers emit and flush all four modes, and failed transitions
leave the driver armed to retry cleanup. The shell mirrors that state, reports
a recoverable user-safe error on failure, and synchronizes an initial
`--no-mouse` request on mount. The adapter contract was checked against
Textual 0.86.0 and the locked 8.2.7.

### Honest refresh and modal-safe global keys

`Ctrl+R` was exposed in the Footer and Help but was a no-op. It now rechecks
only `config_exists(paths.config_path)`, updates the existing Home surface,
and preserves route, active section, focus, and scroll state. It never opens
runtime components or storage and does nothing while a modal is active.

The priority `?` binding could stack Help on top of itself or another modal.
It now toggles the existing Help screen closed and is ignored by other
modals.

### Literal dynamic text

The global error banner, error notification, input-diagnostics current value,
and raw event log previously treated bracketed data as Rich markup. They now
render dynamic text literally, including `[x]`, `[bold]`, and `[/]` payloads.

## Verification

- All focused TUI files: `122 passed`.
- Mouse lifecycle subset: `8 passed`, including all four ON/OFF modes,
  idempotence, initial OS mode, failed enable/disable recovery, and normal and
  exceptional shutdown cleanup.
- Ruff check: passed.
- Ruff format check: 288 files already formatted.
- TUI mypy: 21 source files, no issues.
- CLI parity manifest guard: passed.
- `git diff --check`: passed.
- CLI source and script declarations: no diff.
- The earlier actual CMD and Windows PowerShell maximize/restore smoke evidence
  remains recorded in `2026-07-16-phase2-shell-defects.md`.

The repository-wide non-Ollama suite is not claimed green. Its earlier run did
not complete within ten minutes, and the isolated non-TUI
`test_init_implicit_no_scope_works_from_fresh_dir` still fails while the CLI
tree and that test remain unchanged. This does not block the next TUI phase,
but it remains a merge/release gate outside this Phase 2 correction scope.

## Phase 3 entry notes

- No additional visible Phase 2 code defect was found in the final audit.
- Resolve decision gates 1-3 before RuntimeManager configuration side effects
  and gate 6 before implementing cache invalidation.
- Keep Task Center hidden until real work uses it; make its status symbols
  literal before first exposure.
- Wrap any Phase 3 external-process suspension so application mode is resumed
  even when the suspended body raises.
- Complete PuTTY, Linux, macOS, VS Code, and RDP terminal smoke coverage during
  compatibility hardening; it is not represented as completed here.

## Rollback

Each correction can be removed independently:

- Mouse: remove `tui/mouse.py` and `test_tui_mouse_mode.py`, restore the shell's
  former mouse Boolean and direct sequence writer, and remove the added shell
  mouse regressions. This intentionally restores the documented leak.
- Refresh: restore `action_refresh()` to its former no-op, remove the stable
  Home readiness/guidance IDs and update method, and remove its tests.
- Help: remove the modal guards/toggle branch and its two tests.
- Literal text: remove the relevant `markup=False` arguments and render-line
  assertions.
- Documentation only: remove this file and its link from `docs/tui/README.md`.

Do not alter the original Phase 2 record when applying any rollback.
