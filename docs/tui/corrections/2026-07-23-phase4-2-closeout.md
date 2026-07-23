# TUI Phase 4-2 Clipboard Closeout

- Record ID: `2026-07-23-tui-phase4-2-clipboard-closeout`
- Date: 2026-07-23 (Asia/Seoul)
- Origin: implementation and independent review of the user-approved
  Phase 4-2 clipboard amendment
- Scope: TUI-only copy, cut, paste, selection ownership, clipboard transport,
  Help, and terminal compatibility
- Status: implemented and automated-verification complete; the external
  terminal matrix below remains an explicitly named manual follow-up

## Baseline protection

This is a separate post-baseline implementation record. It does not rewrite
the original 2026-07-15 rebuild plan, the Phase 1 external-contract snapshot,
the Phase 4 closeout, or the approved Phase 4-2 plan amendment.

The ignored local handoff file
`packages/memtomem/src/memtomem/tui/AGENTS.md` contains the bounded amendment
`2026-07-23-tui-phase4-2-clipboard-contract`. Its pre-amendment SHA-256 remains
recorded in the plan amendment, so deleting only that bounded block restores
the earlier handoff.

No file under `memtomem.cli`, no Click declaration, and no console-script
entry changed. No TCSS file changed; Phase 4-2 reused the existing modal and
semantic component families.

## Delivered command and target behavior

- `Ctrl+C` first copies a non-empty selection in the focused editable
  `TuiInput`; otherwise it falls through to an explicit selection on the
  current visible screen.
- Visible read-only Home/Status, Details, Help, warning, error, and diagnostic
  log text use the same application clipboard path.
- A selection from a hidden route, inactive panel, detached widget, or modal
  background is ignored. Search tables gain no invented row or cell
  serialization.
- `Ctrl+X` and `Ctrl+V` operate only on the focused, enabled, effectively
  visible editor on the current screen and active panel.
- No-selection Copy/Cut and read-only Cut/Paste are true no-ops. The final
  Textual `Ctrl+C` quit-help fallback is consumed, so no notification or
  popup appears.
- `Ctrl+Shift+V` and `Shift+Insert` remain hidden paste aliases.
- Terminal paste events are consumed once across Textual's inherited event
  handlers, eliminating duplicate insertion.
- Single-line inputs accept the first logical line from LF, CRLF, or CR
  payloads without modifying the full shared clipboard payload.

## Unified clipboard transport

- Textual's application clipboard remains the in-process mirror and OSC 52
  emitter.
- Copy and Cut also attempt the host OS clipboard. Paste reads that host
  clipboard when it is available and synchronized, then falls back to the
  in-process mirror.
- Windows PowerShell reads use UTF-8 binary transport and
  `[Console]::Out.Write(...)`, so PowerShell does not synthesize a final
  record-ending CRLF or LF. No `rstrip()` is applied to clipboard payloads.
- Empty strings, tabs, Korean/CJK, Unicode, intentional LF, and intentional
  CRLF are preserved by the common transport.
- A failed host write cannot replace a newly copied or cut local value with
  stale, empty, or partially written host data.
- On Windows, the post-write `GetClipboardSequenceNumber` value fences failed
  writes. Zero is treated as unavailable, and sequence values are checked
  both before and after host reads to cover delayed clipboard rendering.
- Without a usable sequence number, the first successful host read after a
  failed write becomes a conservative stale-value fence. A later different
  host value restores host precedence. This no-loss policy intentionally
  favors the local mirror when the environment exposes no change identity.
- Failed copies do not perform a second OS-read subprocess, avoiding a
  compounded four-second timeout path.

## Help and Stitch evidence

Help is the only new discoverability surface. It documents:

- read-only Copy versus editable-only Cut/Paste;
- hidden, inactive, and modal-background no-op behavior;
- `MOUSE:TUI` and `MOUSE:OS`;
- Windows Terminal `Shift`-drag terminal selection while `MOUSE:TUI` remains
  selected;
- conditional OSC 52 support and terminal-native fallbacks.

The first Stitch result invented incorrect F2/F3/F4 meanings and was not used
as behavior evidence. A correction session restored the repository's actual
key contract. Only the corrected hierarchy, density, aligned shortcut rows,
and compact terminal-note placement informed the Help update.

- Stitch project: `7602308868624266029`
- Design system: `assets/23f97e12bb24472da7a882da5bb694e4`
- Corrected Phase 4-2 Help reference:
  `c996cca0b793456d9a8ae1386455b377`
- Generation session: `365698753256551551`
- Contract-correction session: `8027200458216745616`

## Implementation files

Modified production files:

- `packages/memtomem/src/memtomem/tui/clipboard.py`
- `packages/memtomem/src/memtomem/tui/screens/diagnostics.py`
- `packages/memtomem/src/memtomem/tui/screens/shell.py`
- `packages/memtomem/src/memtomem/tui/widgets/controls.py`
- `packages/memtomem/src/memtomem/tui/widgets/modals.py`

New Phase 4-2 tests:

- `packages/memtomem/tests/test_tui_phase42_clipboard_backend.py`
- `packages/memtomem/tests/test_tui_phase42_help.py`
- `packages/memtomem/tests/test_tui_phase42_input.py`
- `packages/memtomem/tests/test_tui_phase42_interactions.py`

The existing input regression was updated in:

- `packages/memtomem/tests/test_tui_cli.py`

Plan and handoff artifacts:

- `docs/tui/amendments/2026-07-23-phase4-2-clipboard-contract.md`
- `docs/tui/README.md`
- ignored local
  `packages/memtomem/src/memtomem/tui/AGENTS.md`

## Memory records

The user explicitly authorized both memory writes. They are separate entries
in `C:\Users\TonyStark\memories\2026-07-23.md`, namespace `default`; neither
rewrites the original rebuild-plan memory.

- Plan amendment:
  `TUI Full Rebuild Plan Amendment — Phase 4-2 Clipboard (2026-07-23)`,
  searchable chunk IDs `163d04af-3682-461a-b1b5-e3c61d3848e6` and
  `eff0cc14-69d8-43eb-ba20-b696ff3a3a3a`.
- Implementation record:
  `Post-baseline implementation record — TUI Phase 4-2 Clipboard (2026-07-23)`,
  searchable chunk IDs `1379867c-b8dd-4a79-8f1f-af231e4f9f6f` and
  `34d3344f-7b79-46ea-9108-c0ff698b21cd`.

## Verification

- Final clipboard, Help, diagnostics, launcher, and external-contract bundle:
  `146 passed`.
- Complete final TUI selection: `332 passed`, `5 skipped`,
  `6376 deselected`.
- The complete TUI run reported four pre-existing pytest deprecation warnings
  caused by the installed `fastembed` package raising a Windows
  `tokenizers` DLL access error during import-or-skip discovery.
- Rendered Help bounds and scroll safety passed at `100x24`, `60x16`,
  `48x12`, `40x10`, and `32x8`.
- Pilot interaction tests exercised editable selection, no selection,
  inactive/hidden/disabled/detached inputs, modal backgrounds, Home/Status,
  Details, Help, warnings, errors, and diagnostic logs.
- Exact transport tests cover empty text, tabs, Korean/CJK, LF, CRLF,
  unavailable commands, timeout, nonzero exit, invalid UTF-8, OSC 52,
  failed/partial host writes, zero revisions, delayed rendering, and
  revisionless recovery.
- Ruff, all-TUI mypy, parity-manifest drift, CLI-source diff, and whitespace
  checks passed in the final closeout run.

## Explicit manual terminal follow-up

The headless Textual harness cannot operate an interactive external terminal
client. The following were therefore not reported as passed:

- post-fix TUI-to-Notepad and Notepad-to-TUI round trips in Windows Terminal;
- the same round trips in legacy conhost, including confirmation that no
  synthesized trailing newline remains;
- Windows Terminal `Shift`-drag while TUI mouse reporting is enabled;
- OSC 52 with terminal permission enabled and disabled;
- PuTTY/SSH, macOS Terminal, Linux Wayland/X11, and XRDP sessions.

The user had already characterized the original difference between Windows
Terminal and conhost before implementation. That observation motivated the
transport fix but is not substituted for a post-fix interactive smoke test.

For a revisionless host, one unavoidable conservative case remains: if the
external clipboard changes exactly once after a failed host write but before
the first successful host read, that first value is fenced until the host
clipboard changes again. This prevents loss of the newly cut local value when
the environment provides no sequence or revision signal. Terminal-provided
paste and terminal-native copy/paste remain available.

## Phase 5 boundary

Phase 4-2 does not authorize or begin Phase 5. The TUI remains independent of
CLI implementation and output formatting. Any Phase 5 entry still requires
its own review and explicit user approval.

## Rollback

1. Revert only the Phase 4-2 hunks in the five modified production files and
   `packages/memtomem/tests/test_tui_cli.py`.
2. Delete the four new Phase 4-2 test files.
3. Delete the bounded
   `2026-07-23-tui-phase4-2-clipboard-contract` amendment block from the
   ignored local TUI `AGENTS.md`.
4. Remove the Phase 4-2 plan and closeout paragraphs from
   `docs/tui/README.md`.
5. Delete the Phase 4-2 plan amendment and this closeout file.
6. Disregard or delete the separately titled Phase 4-2 plan and implementation
   memories; do not rewrite the original rebuild-plan memory.

These steps restore the pre-Phase 4-2 TUI behavior without changing CLI
behavior or any earlier phase record.
