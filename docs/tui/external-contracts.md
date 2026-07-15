# TUI external contracts preserved for the rebuild

> **Post-baseline Phase 1 artifact:** This file records contracts extracted
> after the original 2026-07-15 rebuild plan and memory were written. It does
> not amend either baseline. Roll back this artifact by deleting this file and
> the Phase 1 contract test; the original plan and memory remain unchanged.

Phase 1 freezes behavior that the modular shell must preserve when the old
`app.py` composition is removed. These are compatibility contracts, not an
endorsement of the current page tree or visual design.

## Launcher contract

- `memtomem.cli.tui_cmd` must keep Textual imports lazy so top-level help and
  terminal diagnostics work without the optional TUI dependency.
- The CLI launcher continues to import these public TUI APIs:
  `terminal.choose_border_style`, `terminal.detect_terminal_profile`,
  `terminal.terminal_diagnostics`, `app.run`, `app.run_input_diagnostics`, and
  `runtime.resolve_tui_paths`.
- `run()` accepts keyword-only `border_style`, `mouse`, `terminal_profile`, and
  `paths`. `run_input_diagnostics()` accepts the same arguments except `paths`.
- `mm tui --dev` resolves paths before calling `run`; normal launch leaves
  normal path resolution to the TUI.

Evidence: `test_tui_in_top_level_help`, `test_tui_help_does_not_require_textual`,
`test_tui_diagnose_terminal_does_not_require_textual`,
`test_tui_launch_passes_mouse_option`, and the Phase 1 signature guard.

## Terminal contract

- Auto borders use ASCII on legacy Windows conhost and solid borders on modern
  terminal profiles. Explicit `solid` and `ascii` choices always win.
- Conhost keeps its IME/clipboard/mouse warning and visible-viewport correction.
- Help, warning, confirmation, and diagnostics surfaces honor the chosen border
  style. Diagnostics remain usable without importing Textual.

Evidence: the terminal, conhost, border, warning, and diagnostics tests in
`test_tui_cli.py`, plus the Phase 1 terminal guard.

## Development-path contract

- Dev mode has exactly one state root: `<project>/.dev/.memtomem`.
- Config, `config.d`, database, and memories paths are descendants of that root.
- Config loading, saving, initialization, and component creation must not fall
  back to normal user state or accept a database path outside the dev root.
- Dev mode is valid only at the memtomem project root.

Evidence: the dev launch/config tests in `test_tui_cli.py` and the Phase 1 path
containment guard.

## Focus and keyboard contract

- The logical sections are `nav`, `main`, and `detail`; the old implementation's
  internal `menu` name is not part of the new shell contract.
- F2/F3/F4 activate those sections, F6 and Alt+M toggle mouse mode, and F7/F8
  move tabs only in the active section.
- PageUp/PageDown belong to the active pane. Directional keys follow the
  documented section boundaries and do not steal cursor movement from inputs.
- Remembered focus in an inactive section is never actionable. Mouse clicks
  synchronize section and focus before running their action.
- Escape remains hierarchical, and Ctrl+Q opens a keyboard-operable
  confirmation rather than quitting immediately.

Evidence: the navigation, stale-focus, mouse synchronization, Escape, quit,
page-key, and tab tests in `test_tui_cli.py`, plus the Phase 1 binding guard.

## Clipboard contract

- Focused inputs use the best available OS clipboard for copy, cut, and paste.
- Without input focus, the TUI does not synthesize clipboard operations that
  conflict with terminal-native selection.
- Clipboard helpers are best effort: missing commands, timeouts, subprocess
  errors, and non-zero exits return `None` or `False` rather than crashing.

Evidence: the clipboard helper and focused/unfocused input tests in
`test_tui_cli.py`, plus the Phase 1 public-helper guard.

## Selection contract

- Ordinary lists remain single-selection. Managed roots remain multi-selection.
- Managed-root markers are terminal-safe ASCII: `[ ]` and `[*]`.
- Space and Enter toggle a root. Bulk select, clear, and invert remain
  keyboard-operable. Actions require at least one selected root and apply to all
  selected user-tier roots; project-tier roots are not removable here.

Evidence: the managed-root selection, toolbar, token, reindex, and removal
tests in `test_tui_cli.py`.

## Lifecycle contract

- Components opened by the TUI are closed once when the app unmounts.
- Exclusive worker replacement must receive a callable/factory, not an eagerly
  created coroutine. This prevents a cancelled-before-start worker from leaking
  an unawaited coroutine during shutdown.
- A screen unmount may cancel its presentation workers, but future domain tasks
  must be owned by the global Task Center and survive route changes.
- The dedicated TUI test suite must finish without pending worker, unawaited
  coroutine, component, or storage cleanup warnings.

Evidence: the Phase 1 lazy-worker regression guard and the focused suite run
with `PytestUnraisableExceptionWarning` promoted to an error.

## Stitch review boundary

Stitch project `7602308868624266029` and design system
`assets/23f97e12bb24472da7a882da5bb694e4` were re-read during Phase 1. Their
keyboard-visible actions, fixed/fluid region model, compact fallback, explicit
status language, and non-icon-only controls are compatible with these
contracts. Visual translation remains Phase 2 work; Phase 1 does not preserve
the old visual composition or ID-based styling.
