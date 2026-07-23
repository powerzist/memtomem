"""One clipboard boundary for Textual, OSC 52, and host OS integration."""

from __future__ import annotations

import os
import shutil
import subprocess

_WINDOWS_READ_COMMAND = (
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
    "$value = Get-Clipboard -Raw; "
    "if ($null -ne $value) { [Console]::Out.Write([string]$value) }"
)
_WINDOWS_WRITE_COMMAND = (
    "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false); "
    "Set-Clipboard -Value ([Console]::In.ReadToEnd())"
)
_CLIPBOARD_TIMEOUT_SECONDS = 2


class ClipboardAppMixin:
    """Synchronize Textual's clipboard with the host clipboard when possible.

    Place this mixin before :class:`textual.app.App` in the application's MRO.
    Calling Textual first keeps its in-process mirror current and emits OSC 52
    whenever a terminal driver is attached. Host clipboard access is an
    additional best-effort channel, never a prerequisite for retaining text
    copied inside the running TUI.
    """

    _host_write_failed = False
    _failed_host_revision: int | None = None
    _has_stale_host_snapshot = False
    _stale_host_clipboard: str | None = None

    def copy_to_clipboard(self, text: str) -> None:
        """Copy through Textual/OSC 52, then attempt the host OS clipboard."""

        super().copy_to_clipboard(text)  # type: ignore[misc]
        self._host_write_failed = not write_os_clipboard(text)
        if self._host_write_failed:
            self._failed_host_revision = _host_clipboard_revision()
        else:
            self._failed_host_revision = None
        self._has_stale_host_snapshot = False
        self._stale_host_clipboard = None

    def action_help_quit(self) -> None:
        """Consume Textual's final Ctrl+C fallback when nothing is selected."""

    @property
    def clipboard(self) -> str:
        """Read the host clipboard, falling back to Textual's local mirror."""

        revision_before = _host_clipboard_revision()
        text = read_os_clipboard()
        if text is not None:
            revision_after = _host_clipboard_revision()
            if self._host_write_failed:
                revisions = tuple(
                    revision
                    for revision in (revision_before, revision_after)
                    if revision is not None
                )
                if self._failed_host_revision is not None and revisions:
                    if all(revision == self._failed_host_revision for revision in revisions):
                        return super().clipboard  # type: ignore[misc]
                else:
                    if not self._has_stale_host_snapshot:
                        self._has_stale_host_snapshot = True
                        self._stale_host_clipboard = text
                        return super().clipboard  # type: ignore[misc]
                    if text == self._stale_host_clipboard:
                        return super().clipboard  # type: ignore[misc]
            self._host_write_failed = False
            self._failed_host_revision = None
            self._has_stale_host_snapshot = False
            self._stale_host_clipboard = None
            self._clipboard = text
            return text
        return super().clipboard  # type: ignore[misc]


def read_os_clipboard() -> str | None:
    """Return exact text from the OS clipboard when available."""

    if os.name == "nt":
        return _run_clipboard_command(
            _first_available("powershell.exe", "pwsh"),
            ["-NoProfile", "-Command", _WINDOWS_READ_COMMAND],
        )

    if os.name == "posix":
        if shutil.which("pbpaste"):
            return _run_clipboard_command("pbpaste", [])
        if shutil.which("wl-paste"):
            return _run_clipboard_command("wl-paste", ["--no-newline"])
        if shutil.which("xclip"):
            return _run_clipboard_command("xclip", ["-selection", "clipboard", "-o"])
        if shutil.which("xsel"):
            return _run_clipboard_command("xsel", ["--clipboard", "--output"])

    return None


def write_os_clipboard(text: str) -> bool:
    """Write text to the OS clipboard when available."""

    if os.name == "nt":
        return _send_clipboard_command(
            _first_available("powershell.exe", "pwsh"),
            [
                "-NoProfile",
                "-Command",
                _WINDOWS_WRITE_COMMAND,
            ],
            text,
        )

    if os.name == "posix":
        if shutil.which("pbcopy"):
            return _send_clipboard_command("pbcopy", [], text)
        if shutil.which("wl-copy"):
            return _send_clipboard_command("wl-copy", [], text)
        if shutil.which("xclip"):
            return _send_clipboard_command("xclip", ["-selection", "clipboard"], text)
        if shutil.which("xsel"):
            return _send_clipboard_command("xsel", ["--clipboard", "--input"], text)

    return False


def _first_available(*commands: str) -> str | None:
    for command in commands:
        resolved = shutil.which(command)
        if resolved is not None:
            return resolved
    return None


def _host_clipboard_revision() -> int | None:
    """Return the Windows clipboard sequence number when the API is available."""

    if os.name != "nt":
        return None
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        get_sequence = user32.GetClipboardSequenceNumber
        get_sequence.restype = ctypes.c_uint
        revision = int(get_sequence())
        return revision or None
    except (AttributeError, OSError):
        return None


def _run_clipboard_command(command: str | None, args: list[str]) -> str | None:
    if command is None:
        return None
    try:
        result = subprocess.run(
            [command, *args],
            capture_output=True,
            check=False,
            timeout=_CLIPBOARD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    if result.returncode != 0:
        return None
    stdout = result.stdout
    if isinstance(stdout, bytes):
        try:
            return stdout.decode("utf-8")
        except UnicodeError:
            return None
    return stdout


def _send_clipboard_command(command: str | None, args: list[str], text: str) -> bool:
    if command is None:
        return False
    try:
        result = subprocess.run(
            [command, *args],
            capture_output=True,
            check=False,
            input=text.encode("utf-8"),
            timeout=_CLIPBOARD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return False
    return result.returncode == 0
