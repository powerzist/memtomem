# TUI Panel Keyboard Contract Amendment

Amendment ID: `2026-07-16-tui-panel-keyboard-contract`

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

The baseline directional-key contract allows focus to cross panel boundaries.
With only one enabled Navigation item, a single Down/j press therefore appears
to switch panels rather than move within Navigation. The approved model makes
panel activation explicit and keeps ordinary movement local and predictable.

## Approved replacement contract

- F2, F3, and F4 directly activate Navigation, Main, and Details.
- Arrow keys and h/j/k/l operate only inside the active panel and never change
  the active panel.
- `[` and `]` move to the previous and next panel in the non-wrapping order
  Navigation -> Main -> Details. `[` on Navigation and `]` on Details are
  no-ops.
- Inputs and editors retain native cursor/editing semantics. Literal
  `[]hjkl` input takes priority over shell panel actions.
- Panel-switch actions are disabled while a modal is open; they must never
  mutate the obscured background state.
- Escape is hierarchical:
  1. cancel or close the active modal/overlay;
  2. leave the current input/edit mode;
  3. Details -> Main;
  4. Main -> Navigation;
  5. Navigation -> the same quit-confirmation modal as Ctrl+Q.
- F7/F8 tab movement, PageUp/PageDown scrolling, mouse-section activation,
  remembered focus, and stale inactive-focus protection remain unchanged.

This supersedes the directional section-boundary rules and the previous
panel-level Escape behavior in the TUI keyboard and focus contracts.

## Acceptance checks

- Directional and hjkl input never changes `active_section`.
- Only F2/F3/F4 and non-wrapping `[`/`]` perform direct panel activation.
- Input and TextArea widgets receive literal `[]hjkl` text.
- Modal panel-switch attempts leave background section and focus unchanged.
- Escape follows the approved ladder and Ctrl+Q still confirms before exit.

## Implementation record (2026-07-16)

- `screens/shell.py` removes every directional cross-panel transition, adds
  non-wrapping bracket movement, central modal guards, and the approved Escape
  ladder while preserving native Input/TextArea key ownership.
- `widgets/modals.py` documents F2/F3/F4, panel-local movement, bracket panel
  movement, and the Escape ladder in Help.
- `tests/test_tui_cli.py` covers all three panels, both bracket boundaries,
  literal `[]hjkl` input, modal background protection, and input-first Escape.
- The final focused TUI contract run passed all 110 tests.

## Rollback

1. In `screens/shell.py`, remove the bracket bindings/actions and modal guards,
   restore directional section-boundary transitions and the former
   widget-parent Escape path, then restore the matching Help text and tests.
2. Delete the matching
   `POST-BASELINE AMENDMENT BEGIN` / `POST-BASELINE AMENDMENT END` block from
   `packages/memtomem/src/memtomem/tui/AGENTS.md`.
3. Delete this artifact.

Those steps restore the prior directional-boundary and Escape contracts
without changing the responsive or Task Center amendments.
