"""Stable public launcher for the modular Textual TUI."""

from __future__ import annotations

from memtomem.tui.conhost_driver import install_conhost_resize_driver
from memtomem.tui.runtime import TuiPaths
from memtomem.tui.screens.diagnostics import InputDiagnosticsApp
from memtomem.tui.screens.shell import MemtomemTuiApp
from memtomem.tui.terminal import BorderStyle, detect_terminal_profile
from memtomem.tui.widgets.controls import ModalButton, PanelButton, TuiInput
from memtomem.tui.widgets.modals import (
    ConhostWarningScreen,
    HelpScreen,
    KeybindingsScreen,
    QuitConfirmScreen,
)

__all__ = [
    "ConhostWarningScreen",
    "HelpScreen",
    "InputDiagnosticsApp",
    "KeybindingsScreen",
    "MemtomemTuiApp",
    "ModalButton",
    "PanelButton",
    "QuitConfirmScreen",
    "TuiInput",
    "run",
    "run_input_diagnostics",
]


def run(
    *,
    border_style: BorderStyle = "solid",
    mouse: bool = True,
    terminal_profile: str | None = None,
    paths: TuiPaths | None = None,
) -> None:
    """Run the main Textual application."""
    resolved_profile = terminal_profile or detect_terminal_profile()
    app = MemtomemTuiApp(
        border_style=border_style,
        terminal_profile=resolved_profile,
        mouse_enabled=mouse,
        paths=paths,
    )
    install_conhost_resize_driver(app, resolved_profile)
    app.run(mouse=mouse)


def run_input_diagnostics(
    *,
    border_style: BorderStyle = "solid",
    mouse: bool = True,
    terminal_profile: str | None = None,
) -> None:
    """Run the standalone input diagnostics surface."""
    resolved_profile = terminal_profile or detect_terminal_profile()
    app = InputDiagnosticsApp(
        border_style=border_style,
        terminal_profile=resolved_profile,
        mouse_enabled=mouse,
    )
    install_conhost_resize_driver(app, resolved_profile)
    app.run(mouse=mouse)
