# TUI Compact Layout Contract Amendment

Amendment ID: `2026-07-16-tui-compact-layout-contract`

- Approved: 2026-07-16 (Asia/Seoul)
- Origin: explicit user approval in the TUI Phase 2 correction task
- Scope: TUI only; no CLI behavior or script entry point changes
- Status: implemented and verified on 2026-07-16

## Baseline protection

This is a post-baseline artifact. It does not rewrite the original 2026-07-15
TUI rebuild plan or the existing Phase 2 record.

- `packages/memtomem/src/memtomem/tui/AGENTS.md` pre-amendment SHA-256:
  `a2fd7a2e856838925b4e7a216287b7ff1fad72dea945d943618a17a31c4be9c9`
- `docs/tui/phase2-modular-shell.md` untouched baseline SHA-256:
  `9275485d5572a513ba23976447aefe48efe9d6230639982e7c5f087b10b0a6fe`

## Reason

The baseline 121/80/40-column breakpoints and Phase 2's fixed 26-column
Navigation plus 38-column Task Center hide Details at normal 120x30 and 80x24
terminal defaults. They also collapse to one visible region just below 80
columns. The approved layout places Navigation above the work regions so
common and smaller terminal defaults retain the complete logical shell.

## Approved replacement contract

- `width >= 60` and `height >= 16` is the guaranteed split-layout point:
  one-row horizontal Navigation above simultaneously visible Main and Details.
- At 60-99 columns, Main and Details use an approximately 64/36 fluid split.
- At 100 columns and wider, Details is capped at approximately 36-40 columns
  and Main owns the remaining width.
- Horizontal Navigation is one row, never wraps, owns only its intentional
  horizontal overflow, and automatically reveals the focused route.
- Below either split threshold, render one active panel. F2 Navigation becomes
  a conventional vertical menu; F3 Main and F4 Details use the same persistent
  panel state as split mode.
- Below 32 columns or 8 rows, retain the existing safe-floor resize surface.
- Long menus, lists, and prose may scroll inside their owning region. The shell
  itself must not create terminal-level horizontal or vertical overflow.
- Preserve active route, panel, focus, input, selection, scroll position, and
  running internal state across every responsive transition.
- At constrained widths, compact or hide secondary topbar status before the
  seconds-resolution clock. The hidden TASKS placeholder is not part of the
  width budget.

This supersedes the original 121/80/40 responsive targets and Phase 2's fixed
Navigation/Task Center width decision. It does not change the `<32x8` safe
floor.

## Acceptance checks

- 120x30, 80x24, and 60x16 show horizontal Navigation plus positive Main and
  Details regions without shell overflow.
- 59x16 and 60x15 show only the active panel; F2 uses vertical Navigation.
- 120 -> 60 -> 59 -> 60 -> 120 resize cycles preserve route, focus, input,
  selection, and scroll state and execute no action.
- Help, Quit, errors, seconds-resolution clock, and literal button labels stay
  usable at every guaranteed size.

## Implementation record (2026-07-16)

- `state.py` classifies 100+ columns as wide, 60-99 as dense split, any
  width below 60 or height below 16 as focused, and preserves the existing
  extreme/safe-floor boundaries.
- `screens/shell.py` keeps one persistent Navigation container above
  Main/Details, switches labels and section visibility without recomposition,
  and preserves active/focus state through resize.
- `styles/layout.tcss`, `styles/responsive.tcss`, and
  `styles/components.tcss` implement the one-row menu, 64/36 dense split,
  38-column wide Details cap, and vertical focused Navigation.
- The one-row menu keeps horizontal scrolling but sets its visible scrollbar
  thickness to zero. Without that rule the scrollbar consumed the only row
  and produced a blank blue bar at 60/80/120 columns.
- `tests/test_tui_cli.py` covers 120x30, 80x24, 60x16, 59x16, 60x15,
  repeated resize, region overflow, and exported-SVG Navigation text.
- PNG inspection confirms visible Navigation, Main, Details, seconds clock,
  and modal labels at the approved sizes.
- The final focused TUI contract run passed all 110 tests.

## Rollback

1. In the files listed above, restore the prior 121/80/40 classifications,
   side Navigation/fixed Task Center widths, and old visibility selectors;
   remove the one-row Navigation and its rendered-row tests.
2. Delete the matching
   `POST-BASELINE AMENDMENT BEGIN` / `POST-BASELINE AMENDMENT END` block from
   `packages/memtomem/src/memtomem/tui/AGENTS.md`.
3. Delete this artifact.

Those steps restore the prior responsive targets without changing the Task
Center or keyboard amendments.
