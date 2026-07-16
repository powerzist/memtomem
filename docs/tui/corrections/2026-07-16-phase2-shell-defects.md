# Phase 2 Shell Defect Correction Record

Record ID: `2026-07-16-phase2-shell-defects`

- Applied: 2026-07-16 (Asia/Seoul)
- Origin: user-reported Phase 2 defects followed by read-only root-cause audit
- Scope: TUI only
- Classification: implementation corrections, not baseline product amendments

## Baseline protection

The original `docs/tui/phase2-modular-shell.md` remains untouched at SHA-256
`9275485d5572a513ba23976447aefe48efe9d6230639982e7c5f087b10b0a6fe`.
This separate record documents how the approved baseline contracts were made
to work in the actual renderer and legacy console.

## Corrected defects

### Seconds-resolution clock

`screens/shell.py` already refreshed once per second but formatted only
`HH:MM`. It now renders `HH:MM:SS` in the existing fixed ten-column role.

### Invisible modal button labels

Textual interpreted bracketed labels such as `[ YES ]` as markup and rendered
empty button content. `widgets/modals.py` now escapes the opening bracket so
the decorations and label are literal. Tests inspect `render_line()` for
Close, Yes, No, and Continue rather than checking only widget regions.

### Blank one-row Navigation

The initial one-row layout used an automatic horizontal scrollbar whose
one-cell thickness consumed the menu's only row. The menu now retains internal
horizontal scrolling with zero visible scrollbar thickness. Exported SVG and
PNG checks prove that route labels occupy the row at 120, 80, and 60 columns.

### Classic conhost maximize/restore corruption

Textual 8.2.7 reports `WINDOW_BUFFER_SIZE_EVENT.dwSize`, which can be the
backing buffer rather than the visible `srWindow`. The old application timer
posted a synthetic viewport resize, but a later buffer resize could overwrite
it; its requested-size dedupe then prevented recovery. The same timer mutated
only buffer width and retained buffer height, which could leave OS scrollbars.

The correction:

- adds `tui/conhost_driver.py`, a conhost-only local Windows driver that
  normalizes every incoming Resize to the current read-only `srWindow`;
- adds a read-only 0.1-second observer for window-only changes that emit no
  buffer event;
- installs that driver for both the main app and input diagnostics only on
  classic Windows conhost;
- removes the shell timer, racy requested-size dedupe, and every
  `SetConsole*` backing-buffer mutation;
- keeps Windows Terminal and non-Windows driver selection unchanged.

Actual CMD and Windows PowerShell smoke tests each repeated
120x30 -> 237x63 -> 120x30 five times. Across 89 samples per host, app size,
visible window size, and buffer size matched in every sample; both mismatch
counts were zero. No second-stage buffer mutation was needed.

## Verification

- Focused TUI contract suite: 110 passed.
- Ruff check and format check: passed.
- TUI mypy: 20 source files, no issues.
- CLI parity manifest guard: passed.
- `git diff --check`: passed.
- Full non-Ollama suite reached 90% before its 10-minute limit and emitted
  failures without reaching a final inventory. The first isolated failure was
  `test_init_implicit_no_scope_works_from_fresh_dir`, where an existing
  `context.md` triggered an overwrite prompt after 695 passes and 6 skips; it
  is outside the focused TUI set. The full suite is therefore not recorded as
  green even though all focused TUI contracts passed.

## Rollback

Rollback each correction independently:

- Clock: change the shell format from `%H:%M:%S` back to `%H:%M` and remove
  the seconds assertion.
- Buttons: remove the literal bracket escaping and the render-line assertions.
- One-row menu: remove `scrollbar-size-horizontal: 0` and its exported-render
  regression test.
- Conhost: remove `conhost_driver.py` and its tests, remove the two launcher
  installation calls, and restore the previous shell timer plus terminal
  width-normalization helper only if intentionally accepting the documented
  corruption and scrollbar regressions.

Delete this file after completing the selected rollback. The three product
contract amendments remain independently removable through their own markers.
