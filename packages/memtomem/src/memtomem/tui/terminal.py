"""Terminal capability helpers for the Textual UI."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import IO, Literal, cast

import click

BorderMode = Literal["auto", "solid", "ascii"]
BorderStyle = Literal["solid", "ascii"]

VALID_BORDER_MODES: tuple[BorderMode, ...] = ("auto", "solid", "ascii")
VALID_BORDER_STYLES: tuple[BorderStyle, ...] = ("solid", "ascii")


def detect_terminal_profile(
    env: Mapping[str, str] | None = None,
    *,
    os_name: str | None = None,
) -> str:
    """Return a coarse terminal profile for UI compatibility decisions."""

    env = os.environ if env is None else env
    os_name = os.name if os_name is None else os_name

    if os_name == "nt":
        if env.get("WT_SESSION"):
            return "windows-terminal"
        if env.get("TERM_PROGRAM") == "vscode":
            return "vscode-terminal"
        if env.get("SSH_TTY") or env.get("SSH_CONNECTION"):
            return "ssh"
        if env.get("ConEmuANSI") or env.get("CMDER_ROOT"):
            return "conemu-cmder"
        return "windows-conhost"

    if env.get("TERM_PROGRAM") == "vscode":
        return "vscode-terminal"
    if env.get("SSH_TTY") or env.get("SSH_CONNECTION"):
        return "ssh"

    term = env.get("TERM", "")
    if "xterm" in term or "screen" in term or "tmux" in term:
        return "modern-terminal"
    return "unix-terminal"


def has_ime_limitations(profile: str) -> bool:
    """Return True when the terminal profile has known IME input limitations."""

    return profile == "windows-conhost"


def windows_console_viewport_size(stream: IO[str] | None = None) -> tuple[int, int] | None:
    """Return the visible classic-console viewport size, not its backing buffer.

    Textual's Windows driver derives resize events from ``dwSize`` in
    ``WINDOW_BUFFER_SIZE_EVENT``. Classic conhost can restore the visible
    window after Alt+Enter while leaving that buffer at the fullscreen size.
    ``srWindow`` is the authoritative visible viewport in that state.
    """
    if os.name != "nt":
        return None

    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Coord(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class SmallRect(ctypes.Structure):
        _fields_ = [
            ("Left", wintypes.SHORT),
            ("Top", wintypes.SHORT),
            ("Right", wintypes.SHORT),
            ("Bottom", wintypes.SHORT),
        ]

    class ConsoleScreenBufferInfo(ctypes.Structure):
        _fields_ = [
            ("dwSize", Coord),
            ("dwCursorPosition", Coord),
            ("wAttributes", wintypes.WORD),
            ("srWindow", SmallRect),
            ("dwMaximumWindowSize", Coord),
        ]

    output = stream if stream is not None else sys.__stdout__
    if output is None:
        return None
    try:
        handle = msvcrt.get_osfhandle(output.fileno())
    except (AttributeError, OSError, ValueError):
        return None
    info = ConsoleScreenBufferInfo()
    if not ctypes.windll.kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
        return None
    return (
        info.srWindow.Right - info.srWindow.Left + 1,
        info.srWindow.Bottom - info.srWindow.Top + 1,
    )


def choose_border_style(
    requested: BorderMode = "auto",
    env: Mapping[str, str] | None = None,
    *,
    os_name: str | None = None,
) -> BorderStyle:
    """Choose the Textual border style for the current terminal."""

    env = os.environ if env is None else env
    if requested in VALID_BORDER_STYLES:
        return requested

    env_override = env.get("MEMTOMEM_TUI_BORDER", "").lower()
    if env_override in VALID_BORDER_STYLES:
        return cast(BorderStyle, env_override)

    profile = detect_terminal_profile(env, os_name=os_name)
    if profile == "windows-conhost":
        return "ascii"
    return "solid"


def terminal_diagnostics(
    requested: BorderMode = "auto",
    env: Mapping[str, str] | None = None,
    *,
    os_name: str | None = None,
) -> str:
    """Build a short diagnostic report for terminal rendering issues."""

    env = os.environ if env is None else env
    os_name = os.name if os_name is None else os_name
    profile = detect_terminal_profile(env, os_name=os_name)
    border = choose_border_style(requested, env, os_name=os_name)
    keys = (
        "WT_SESSION",
        "TERM_PROGRAM",
        "TERM",
        "SSH_TTY",
        "SSH_CONNECTION",
        "ConEmuANSI",
        "CMDER_ROOT",
        "MEMTOMEM_TUI_BORDER",
    )
    lines = [
        "memtomem TUI Terminal Diagnostics",
        "=================================",
        "",
        "Detection",
        "---------",
        f"OS:               {os_name}",
        f"Profile:          {profile}",
        f"Requested border: {requested}",
        f"Chosen border:    {border}",
        "",
        "Environment",
        "-----------",
    ]
    lines.extend(f"{key + ':':<22} {env.get(key, '') or '(unset)'}" for key in keys)
    lines.extend(
        [
            "",
            "Rendering probes",
            "----------------",
            "1. Plain Unicode box drawing",
            "┌────────┐",
            "│ solid  │",
            "└────────┘",
            "",
            "2. ANSI-colored Unicode box drawing",
            "┌────────┐",
            "│ solid  │",
            "└────────┘",
            "",
            "3. Adjacent colored panels, closer to the TUI layout",
            "┌────────┐ ┌────────┐ ┌────────┐",
            "│ active │ │ panel  │ │ detail │",
            "└────────┘ └────────┘ └────────┘",
            "",
            "4. ASCII fallback",
            "+--------+",
            "| ascii  |",
            "+--------+",
            "",
            "Interpretation",
            "--------------",
            "If probe 1 looks correct but probes 2 or 3 lose vertical lines,",
            "the terminal can print Unicode box characters, but styled TUI rendering is unstable.",
            "Use `mm tui --border ascii` in that terminal, or prefer Windows Terminal.",
        ]
    )
    return _style_terminal_diagnostics("\n".join(lines))


def _style_terminal_diagnostics(output: str) -> str:
    """Apply CLI-only styling in the same spirit as ``mm status``."""

    if "NO_COLOR" in os.environ:
        return output

    styled: list[str] = []
    current_probe: str | None = None

    for line in output.splitlines():
        if line == "memtomem TUI Terminal Diagnostics":
            styled.append(click.style(line, fg="cyan", bold=True))
        elif line == "=================================":
            styled.append(click.style(line, fg="cyan", bold=True))
        elif line in {"Detection", "Environment", "Rendering probes"}:
            current_probe = None
            styled.append(click.style(line, bold=True))
        elif line in {"---------", "-----------", "----------------"}:
            styled.append(click.style(line, bold=True))
        elif line == "Interpretation":
            current_probe = None
            styled.append(click.style(line, fg="yellow", bold=True))
        elif line == "--------------":
            styled.append(click.style(line, fg="yellow", bold=True))
        elif line.startswith("1. "):
            current_probe = "plain"
            styled.append(click.style(line, bold=True))
        elif line.startswith("2. "):
            current_probe = "ansi"
            styled.append(click.style(line, bold=True))
        elif line.startswith("3. "):
            current_probe = "adjacent"
            styled.append(click.style(line, bold=True))
        elif line.startswith("4. "):
            current_probe = "ascii"
            styled.append(click.style(line, bold=True))
        elif _is_box_sample_line(line):
            styled.append(_style_probe_line(line, current_probe))
        elif line.startswith("If probe 1"):
            styled.append(click.style(line, fg="yellow"))
        elif line.startswith("Use `mm tui --border ascii`"):
            styled.append(_style_command_hint(line))
        else:
            styled.append(_style_diagnostic_key_value(line))

    return "\n".join(styled)


def _style_diagnostic_key_value(line: str) -> str:
    if ":" not in line or line.startswith("http"):
        return line

    key, value = line.split(":", 1)
    if not key or " " in key.strip() and not key.endswith("border"):
        return line

    if key in {"Chosen border", "Profile"}:
        return click.style(f"{key}:", bold=True) + click.style(value, fg="cyan")
    return click.style(f"{key}:", bold=True) + value


def _is_box_sample_line(line: str) -> bool:
    return any(char in line for char in "┌┐└┘│─+-|")


def _style_probe_line(line: str, probe: str | None) -> str:
    if probe == "ansi":
        return click.style(line, fg="cyan")
    if probe == "adjacent":
        return _style_adjacent_probe_line(line)
    if probe == "ascii":
        return click.style(line, fg="green")
    return line


def _style_adjacent_probe_line(line: str) -> str:
    if len(line) < 32:
        return click.style(line, fg="cyan")
    return (
        click.style(line[:10], fg="cyan")
        + line[10:11]
        + click.style(line[11:21], fg="bright_black")
        + line[21:22]
        + click.style(line[22:], fg="bright_black")
    )


def _style_command_hint(line: str) -> str:
    return line.replace(
        "`mm tui --border ascii`",
        click.style("`mm tui --border ascii`", fg="cyan", bold=True),
    )
