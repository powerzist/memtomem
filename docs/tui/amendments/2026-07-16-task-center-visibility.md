# TUI Task Center Visibility Amendment

Amendment ID: `2026-07-16-tui-task-center-visibility`

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

The Phase 2 record is intentionally left unchanged. It remains evidence of
what Phase 2 originally delivered.

## Reason

Phase 2 exposes a persistent `TASKS: 0` status and a Task Center even though
domain task execution and cancellation tokens are Phase 3 work and no
production TUI path currently creates a task. The placeholder consumes scarce
terminal space and presents an inactive implementation scaffold as a user
feature.

## Approved replacement contract

- Hide all user-visible `TASKS` status until real domain work is connected to
  the task registry.
- Do not present the current Task Center as the F4 panel during this phase.
- Retain the task registry as dormant internal infrastructure; do not delete
  its typed records or lifecycle semantics.
- Use F4 for a read-mostly contextual Details panel. Details may expose
  selected-item explanation, status, metadata, disabled-feature reasons, and
  keyboard guidance. It must not pretend that deferred workflows are active.
- Reintroducing persistent task status or a Task Center requires a later,
  explicit product decision once actual background operations use it.

This supersedes only the current visibility and F4 placement of the rebuild
plan's persistent Task Center. It does not cancel the long-term task ownership
contract.

## Acceptance checks

- No `TASKS` label or zero-count placeholder is rendered in the shell.
- F4 activates contextual Details in split and focused layouts.
- Dormant task registry tests continue to pass independently of the shell.
- Deferred destinations remain visibly deferred and are not described as
  completed features.

## Implementation record (2026-07-16)

- `screens/shell.py` removes the topbar task count and visible Task Center,
  composes `DetailsSurface` in F4, and retains the injected `TaskCenter` as
  headless application state.
- `state.py` remembers `details-surface` as the F4 focus target.
- `styles/components.tcss` gives Home and Details the same persistent,
  scroll-owning surface geometry.
- `tests/test_tui_cli.py` proves that no task badge or task row is rendered,
  F4 owns Details, and task records survive resize without becoming visible.
- The final focused TUI contract run passed all 110 tests.

## Rollback

1. In the files listed above, restore the topbar task-count widget and the
   Task Center view/subscription while leaving the internal `TaskCenter`
   registry intact; remove `DetailsSurface` and restore the prior detail focus
   ID and task-view assertions.
2. Delete the matching
   `POST-BASELINE AMENDMENT BEGIN` / `POST-BASELINE AMENDMENT END` block from
   `packages/memtomem/src/memtomem/tui/AGENTS.md`.
3. Delete this artifact.

Those steps restore the prior visible Task Center contract without removing
the other independently approved amendments.
