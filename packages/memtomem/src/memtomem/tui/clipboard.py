"""Best-effort OS clipboard helpers for the Textual UI."""

from __future__ import annotations

import os
import shutil
import subprocess


def read_os_clipboard() -> str | None:
    """Return text from the OS clipboard when available."""

    if os.name == "nt":
        return _run_clipboard_command(
            _first_available("powershell.exe", "pwsh"),
            ["-NoProfile", "-Command", "Get-Clipboard -Raw"],
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
                "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
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


def _run_clipboard_command(command: str | None, args: list[str]) -> str | None:
    if command is None:
        return None
    try:
        result = subprocess.run(
            [command, *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _send_clipboard_command(command: str | None, args: list[str], text: str) -> bool:
    if command is None:
        return False
    try:
        result = subprocess.run(
            [command, *args],
            capture_output=True,
            check=False,
            input=text,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0
