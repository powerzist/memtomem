# Phase 2 modular shell record

> **Post-baseline Phase 2 artifact:** This file records implementation work
> performed after the original 2026-07-15 rebuild plan and memory were written.
> It does not amend either baseline. Roll back this artifact by reverting the
> Phase 2 TUI code and tests and deleting this file; the original plan and
> memory remain unchanged.

Phase 2 replaces the old visual composition with a modular Textual shell. It
does not implement a CLI parity workflow and does not change a parity-manifest
row.

## Delivered boundaries

- `app.py` is now only the stable launcher and public compatibility exports.
- `screens/shell.py` owns the responsive shell, route state/selection scaffold,
  section focus, global errors, Help/Quit entry points, and terminal viewport
  adaptation. Home is the only enabled route until native workflows arrive;
  disabled inventory is not treated as completed routing parity.
- `state.py` owns session-scoped route, layout, active-section, remembered
  focus, mouse, and error state.
- `application/tasks.py` owns structured Task Center records independently of
  a visible route, including navigation, resize, exit, and cancellation
  policies. Registry notifications keep the Task Center and persistent topbar
  count current. Domain task execution and cancellation tokens remain Phase 3
  work.
- `widgets/` owns reusable control, navigation, modal, and task families.
- `styles/` is physically and logically split into tokens, layout, components,
  states, and responsive layers. Widget-qualified palette rules are used;
  individual button and route IDs are not styled. The pinned Textual version
  accepts multiple paths but scopes TCSS variables per path, so the ordered
  layers are joined at load time to keep one authoritative token layer.

The old temporary Test page, folder-browser prototype, color preview, static
command catalog, and monolithic stylesheet were removed. Unimplemented primary
destinations are visible only as disabled routing inventory marked with `-`;
they are not presented as completed parity.

## Stitch evidence

Phase 2 re-read project `7602308868624266029` and design system
`assets/23f97e12bb24472da7a882da5bb694e4`, then generated review session
`8591401531631166322`. The implementation translated these design decisions:

- 26-column navigation, fluid main region, and 38-column Task Center when wide;
- restrained dark surfaces, thin neutral borders, and cyan reserved for focus
  and primary action;
- text plus symbol plus semantic color for task state;
- explicit text actions in Help and Quit surfaces;
- one visible region at compact widths.

Stitch suggested an 80x24 safe floor. That conflicted with the authoritative
plan, so the implementation keeps the approved floor below 32 columns or 8
rows and treats 32x8 as the extreme-small layout.

## Phase boundary

Home deliberately does not open or migrate storage in Phase 2. It reports
whether configuration exists and explains that read-only Home/Status and full
Search arrive in Phase 4. Native setup remains Phase 5. This preserves the
approved decision-gate 9 boundary without importing, launching, or paraphrasing
CLI flows.

## Phase 2 audit corrections

A plan-to-implementation audit on 2026-07-15 found and corrected shell defects
that the initial Phase 2 tests did not detect:

- modals are centered and their actions remain inside the dialog at `32x8` and
  the safe-floor height;
- `40x10` and wide-but-shallow terminals use the extreme layout, with a
  single scroll-owning navigation pane, short labels, and non-wrapping topbar;
- safe-floor focus moves to a visible focusable target and returns to the
  remembered active-section target after resize;
- global errors live outside the optional detail pane and remain visible when
  compact layouts hide that pane;
- disabled-route, ASCII active-border, stale-focus keyboard, pointer-section,
  hierarchical Escape, and fixed-width topbar regressions are covered;
- the public input diagnostics surface again records key/paste events, current
  value, and legacy-console IME guidance;
- launcher, lazy-dependency, dev-path, conhost, modal, responsive-region, task
  refresh, and cleanup guards were restored or widened after the old monolith
  tests were removed.
