# TUI Phase 4-2 Clipboard Contract Amendment

Amendment ID: `2026-07-23-tui-phase4-2-clipboard-contract`

- Approved: 2026-07-23 (Asia/Seoul)
- Origin: explicit user decisions during the Phase 4-2 planning discussion
- Scope: TUI-wide text copy, editable-field cut/paste, clipboard transport,
  Help discoverability, and terminal compatibility only
- Status: approved for implementation before Phase 5

## Baseline protection

This is a separate post-baseline artifact. It inserts Phase 4-2 between the
completed Phase 4 and the not-yet-started Phase 5 without rewriting the
original 2026-07-15 rebuild plan, the Phase 1 compatibility snapshot, or the
Phase 4 closeout.

- `packages/memtomem/src/memtomem/tui/AGENTS.md` pre-amendment SHA-256:
  `cb27826feb90a643e36f7f8aa7d77c222cbc0227c5d3f2d5c29bf00b04a3bf83`
- `docs/tui/external-contracts.md` untouched Phase 1 snapshot SHA-256:
  `9b6af90892cca300160af5c48662620d533b2d778c5af48f5c546f17d9982088`
- `docs/tui/corrections/2026-07-23-phase4-closeout.md` untouched SHA-256:
  `474e263ee46dca461bbb19305e14da767151483de0881b28d86828042bc5a813`

The Phase 1 clipboard text remains an accurate historical characterization of
the implementation at that time. This amendment explicitly supersedes its
"focused inputs only" and "no synthesized clipboard behavior without input
focus" rules for current TUI behavior. It does not change list-selection,
launcher, terminal, development-path, or lifecycle contracts.

Phase 5 remains blocked until Phase 4-2 has its own verified closeout and
separate implementation record.

## Approved command and target contract

Clipboard shortcuts are available throughout the TUI, but they resolve exactly
one valid target on the current visible screen. They are never broadcast to
widgets.

### Copy

- `Ctrl+C` copies an explicit non-empty text selection from the current visible
  screen.
- Valid sources include a selection in an editable field and a Textual screen
  selection over visible read-only text such as Home/Status, Details, Help,
  warnings, errors, and logs.
- An editable selection takes its normal focused-widget path. Otherwise the
  current screen selection is used.
- A selection belonging only to a hidden route, inactive panel, detached
  widget, or modal background is not a valid source.
- No selection is a no-op. Do not infer "copy the whole field", "copy the whole
  panel", or "copy the current row".
- Search `DataTable` rows and cells do not gain an automatic serialization
  format. Users copy literal result text from F4 Details or use terminal-native
  selection in `MOUSE:OS`.

### Cut

- `Ctrl+X` operates only on a non-empty selection in the focused, enabled,
  visible editable field on the active screen and active panel.
- Read-only text, hidden or inactive editors, and modal-background editors are
  no-ops.
- The selected text enters the common clipboard path before deletion. The
  synchronized in-app mirror prevents loss when an external clipboard channel
  is unavailable.

### Paste

- `Ctrl+V` operates only on the focused, enabled, visible editable field on the
  active screen and active panel.
- `Ctrl+Shift+V` and `Shift+Insert` remain silent compatibility aliases.
- Terminal-provided paste events and shortcut-driven paste must not insert the
  same payload twice.
- Read-only text, hidden or inactive editors, and modal-background editors are
  no-ops. The TUI never pastes into a remembered old input.

## Exact text and single-line Input contract

- Clipboard transport must preserve the exact text supplied by the clipboard.
- Windows PowerShell/conhost output-record termination must not add a CRLF or
  LF to clipboard text. Fix the command transport so it writes the clipboard
  value to stdout without a record terminator.
- Do not use a blanket `rstrip()` or similar cleanup. A final newline that the
  user actually copied remains part of the clipboard payload.
- A single-line Textual `Input` accepts only the first logical line from a
  genuinely multiline payload, matching Textual's normal paste-event behavior.
- A future multiline editor must preserve genuine line breaks; the single-line
  policy must not leak into the shared clipboard transport.
- Preserve empty strings, tabs, Korean/CJK text, Unicode, and both LF and CRLF
  payloads without encoding loss.

## One user-visible clipboard with layered terminal support

All TUI copy/cut/paste surfaces use one common clipboard boundary:

1. Textual's application clipboard is the synchronized in-process mirror and
   fallback.
2. Copy also attempts the host OS clipboard so a locally running TUI
   interoperates with applications such as Notepad.
3. Copy emits Textual's OSC 52 sequence unconditionally. A terminal that
   supports and permits OSC 52 may bridge remote TUI copy to the user's local
   clipboard; a terminal that disables or lacks it simply does not provide
   that channel.
4. Paste prefers a terminal-provided paste event when the terminal consumes
   its native paste shortcut. A shortcut delivered to the TUI reads the host
   OS clipboard and falls back to the synchronized in-process mirror when the
   host clipboard is unavailable.

No TUI process can force a remote terminal client to expose its local
clipboard. OSC 52 support and security settings remain terminal-owned.
Unsupported or restricted environments must fail safely and retain:

- terminal-native copy/paste;
- `MOUSE:OS`;
- the terminal's configured paste action;
- the in-process mirror for text copied within the running TUI.

`MOUSE:TUI` remains the widget-interaction and application-selection mode.
`MOUSE:OS` remains the explicit terminal-native selection/copy/paste mode. Help
must also explain that Windows Terminal users may hold `Shift` while dragging
to request terminal/OS selection even while TUI mouse reporting is enabled.

## Help and presentation contract

- Clipboard shortcuts are documented once in Help.
- `Ctrl+C`, `Ctrl+X`, and `Ctrl+V` are the primary rows.
- Compatibility paste aliases are secondary text.
- Help distinguishes read-only Copy from editable-only Cut/Paste and states
  that hidden, inactive, and modal-background widgets are never targeted.
- Help contains concise `MOUSE:TUI`, `MOUSE:OS`, Windows Terminal
  `Shift`-drag, OSC 52 conditional-support, and safe-fallback notes.
- Input clipboard bindings are hidden from the Footer. Do not add a toolbar,
  Topbar badge, page-local instructions, success popup, or clipboard settings
  surface.
- Reuse the existing modal structure and semantic classes. Phase 4-2 does not
  justify ID-specific CSS or a new color/component family.

Stitch was used as a hierarchy and density review partner:

- project: `7602308868624266029`
- design system: `assets/23f97e12bb24472da7a882da5bb694e4`
- Phase 4-2 Help reference: `c996cca0b793456d9a8ae1386455b377`
- generation session: `365698753256551551`
- contract-correction session: `8027200458216745616`

The first generated board invented incorrect F2/F3/F4 meanings. The correction
session replaced them with the repository's actual key contract. Only the
corrected hierarchy, aligned rows, primary/secondary emphasis, and compact
terminal-note placement are valid evidence. Repository behavior and rendered
Textual output remain authoritative.

## Implementation sequence

1. Freeze the command/target contract and characterize current Textual
   selection, Input, OS clipboard, OSC 52, terminal-paste, modal, and active
   panel behavior.
2. Correct exact clipboard transport and make single-line Input handling match
   the approved first-line policy without deleting intentional trailing
   newlines from the shared payload.
3. Route editable and read-only copy through the common clipboard boundary,
   retain editable-only cut/paste, and enforce active-screen, active-panel,
   visibility, focus, and modal ownership.
4. Apply the Help-only discoverability policy using the existing modal and
   semantic TCSS families.
5. Verify automated behavior, rendered interaction, terminal boundaries, CLI
   isolation, and rollback evidence before recording closeout.

## Acceptance checks

- Copy and paste round-trip between a locally running TUI and the host OS
  clipboard without a synthesized final newline.
- PowerShell/conhost-style clipboard transport adds no record-ending CRLF/LF.
- Windows Terminal behavior remains correct when its native paste shortcut
  delivers a paste event.
- Single-line Input takes the first line of a genuine multiline paste; the
  shared clipboard still retains the complete exact payload.
- Details, Help, Home/Status, warning, error, and log selections can use
  `Ctrl+C`.
- Read-only `Ctrl+X`/`Ctrl+V`, no-selection Copy/Cut, hidden routes, inactive
  panels, detached widgets, and modal backgrounds are no-ops.
- Search tables do not acquire an invented row/cell copy representation.
- OSC 52 is emitted without requiring a TUI setting and remains conditional on
  terminal support/permission.
- `MOUSE:TUI`, `MOUSE:OS`, Windows Terminal `Shift`-drag guidance, and fallback
  limits are visible in Help at supported viewports.
- Footer does not expose Copy/Cut/Paste labels.
- Focused tests, rendered pilot tests, the complete TUI suite, Ruff, manifest
  drift, CLI-source diff, and import-boundary guards pass.

Actual terminal evidence should cover Windows Terminal and legacy conhost in
the local environment. PuTTY/SSH, macOS, Linux, and XRDP remain required
compatibility targets; any environment unavailable during this implementation
must be named as an unverified manual follow-up rather than reported as passed.

## Rollback

1. Revert only the Phase 4-2 implementation files named in its closeout record.
2. Delete the matching
   `POST-BASELINE AMENDMENT BEGIN` / `POST-BASELINE AMENDMENT END` block from
   `packages/memtomem/src/memtomem/tui/AGENTS.md`.
3. Remove this artifact's paragraph from `docs/tui/README.md`.
4. Delete this artifact.
5. If a separate memtomem amendment memory was added after implementation,
   disregard or delete that separately titled memory; never rewrite the
   original rebuild-plan memory.

Those steps restore the pre-Phase 4-2 plan and historical Phase 1/Phase 4
records without altering CLI behavior.
