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
