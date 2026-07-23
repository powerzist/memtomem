# TUI rebuild audit artifacts

`parity-manifest.json` is the machine-checked inventory for the independent
Textual TUI rebuild. It records every current Click path, hidden command and
option, separate console script, and shell-only behavior that needs an explicit
parity disposition. Behavioral fields intentionally begin as `unreviewed` and
must be completed from CLI/core code and characterization tests before a TUI
workflow is implemented.

`cli-baseline.json` freezes the CLI source files and `[project.scripts]`
declarations at the start of the rebuild. It exists to prove TUI work did not
silently change the CLI. Updating it requires a separately approved CLI change.

`decision-gates.md` characterizes the eleven audited behavior conflicts. It is
not an authorization record: each pending gate still requires an explicit user
decision before the corresponding TUI workflow is implemented.

`external-contracts.md` is the Phase 1 compatibility map for launcher,
terminal, dev paths, focus, clipboard, selection, and lifecycle behavior that
must survive replacement of the old Textual composition.

`phase2-modular-shell.md` records the post-baseline modular shell, Stitch
evidence, semantic stylesheet boundaries, and the deliberate Phase 2/3/4/5
feature boundary.

`corrections/2026-07-16-phase2-closeout.md` is the rollback-safe Phase 2 exit
record. It captures the final mouse lifecycle, Refresh, modal-key, and literal
rendering corrections, their verification, and the remaining Phase 3 entry
notes without modifying the original Phase 2 record.

`amendments/2026-07-16-phase3-runtime-contracts.md` separately records the
approved Phase 3 result/cancellation states, permanent-until-reapproved TASKS
boundary, Gate 6 result-cache policy, and Stitch evidence limits. It leaves the
original plan and decision-gate audit unchanged.

`corrections/2026-07-16-phase3-closeout.md` records the implemented typed
contracts, operation/runtime ownership, multi-generation Gate 6 behavior, DEV
model-cache isolation, shared Textual components, verification evidence, and
exact rollback boundary for Phase 3.

`corrections/2026-07-23-phase4-closeout.md` records the completed read-only
Home/Status and real Search vertical slice, approved Top K/format/reranker/
cancellation decisions, Stitch references, rendered interaction evidence,
configuration-safety corrections, verification limits, Phase 5 boundary, and
exact rollback steps.

`amendments/2026-07-23-phase4-2-clipboard-contract.md` inserts the
user-approved TUI-wide clipboard phase between Phase 4 and Phase 5. It records
read-only Copy versus editable-only Cut/Paste, active/visible target ownership,
exact PowerShell/conhost text transport, single-line paste behavior, unified
OS/Textual/OSC 52 fallbacks, Help-only discoverability, corrected Stitch
evidence, verification requirements, and exact rollback steps.

`corrections/2026-07-23-phase4-2-closeout.md` records the implemented common
clipboard boundary, exact Windows transport, stale-host loss protection,
editable and read-only target routing, Help/Stitch evidence, automated
verification, explicit interactive-terminal follow-ups, and rollback steps
without changing CLI or TCSS.

Regenerate the inventory after an approved CLI-tree change:

```powershell
uv run python tools/tui_parity_manifest.py
```

Accept a separately approved CLI baseline change:

```powershell
uv run python tools/tui_parity_manifest.py --accept-cli-baseline
```

CI-style drift check:

```powershell
uv run python tools/tui_parity_manifest.py --check
```
