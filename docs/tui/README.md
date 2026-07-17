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
