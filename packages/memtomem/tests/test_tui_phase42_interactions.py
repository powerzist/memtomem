"""Active-screen and active-panel copy routing for TUI Phase 4-2."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from textual.actions import SkipAction
from textual.geometry import Offset
from textual.selection import Selection
from textual.widgets import Static

from memtomem.tui.runtime import TuiPaths
from memtomem.tui.screens.diagnostics import InputDiagnosticsApp
from memtomem.tui.screens.shell import ActiveSelectionScreen, MemtomemTuiApp
from memtomem.tui.state import ErrorNotice
from memtomem.tui.widgets.modals import ConhostWarningScreen, HelpScreen


def _paths(tmp_path: Path) -> TuiPaths:
    root = tmp_path / ".memtomem"
    root.mkdir()
    (root / "config.json").write_text("{}\n", encoding="utf-8")
    return TuiPaths(
        mode="dev",
        project_root=tmp_path,
        state_root=root,
        config_path=root / "config.json",
        config_d_path=root / "config.d",
        database_path=root / "memtomem.db",
        memories_path=root / "memories",
    )


def _select(widget: Static, text: str) -> None:
    widget.update(text)
    widget.screen.selections = {widget: Selection.from_offsets(Offset(0, 0), Offset(len(text), 0))}


def _capture_copy(
    monkeypatch: pytest.MonkeyPatch,
    app: MemtomemTuiApp,
) -> tuple[list[str], Callable[[str], None]]:
    copied: list[str] = []

    def capture(text: str) -> None:
        copied.append(text)

    monkeypatch.setattr(app, "copy_to_clipboard", capture)
    return copied, capture


async def test_read_only_selection_copies_only_from_active_visible_panel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-terminal",
        paths=_paths(tmp_path),
    )

    async with app.run_test(size=(120, 30)) as pilot:
        default_screen = app.screen
        assert isinstance(default_screen, ActiveSelectionScreen)
        detail_text = app.query_one("#home-detail-content", Static)
        copied, _ = _capture_copy(monkeypatch, app)

        app.activate_section("detail")
        _select(detail_text, "visible detail")
        await pilot.press("ctrl+c")
        assert copied == ["visible detail"]

        app.activate_section("main")
        with pytest.raises(SkipAction):
            default_screen.action_copy_text()
        assert copied == ["visible detail"]

        app.activate_section("detail")
        detail_text.display = False
        with pytest.raises(SkipAction):
            default_screen.action_copy_text()
        assert copied == ["visible detail"]


async def test_modal_background_selection_is_ignored_but_modal_text_can_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-terminal",
        paths=_paths(tmp_path),
    )

    async with app.run_test(size=(100, 24)) as pilot:
        default_screen = app.screen
        assert isinstance(default_screen, ActiveSelectionScreen)
        detail_text = app.query_one("#home-detail-content", Static)
        app.activate_section("detail")
        _select(detail_text, "background detail")
        copied, _ = _capture_copy(monkeypatch, app)

        app.push_screen(HelpScreen())
        await pilot.pause()

        with pytest.raises(SkipAction):
            default_screen.action_copy_text()
        assert copied == []

        help_screen = app.screen
        assert isinstance(help_screen, HelpScreen)
        help_body = next(
            widget
            for widget in help_screen.query(Static)
            if "EDIT & CLIPBOARD" in str(widget.content)
        )
        _select(help_body, "modal help")
        await pilot.press("ctrl+c")
        assert copied == ["modal help"]


async def test_home_error_and_warning_text_use_the_same_copy_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-terminal",
        paths=_paths(tmp_path),
    )

    async with app.run_test(size=(100, 24)) as pilot:
        copied, _ = _capture_copy(monkeypatch, app)

        app.activate_section("main")
        readiness = app.query_one("#home-readiness", Static)
        _select(readiness, "home status")
        await pilot.press("ctrl+c")
        assert copied == ["home status"]

        app.report_error(
            ErrorNotice(
                code="TUI-TEST",
                message="visible error",
                detail=None,
                recoverable=True,
            )
        )
        error = app.query_one("#global-error", Static)
        _select(error, "visible error")
        await pilot.press("ctrl+c")
        assert copied == ["home status", "visible error"]

        app.push_screen(ConhostWarningScreen())
        await pilot.pause()
        warning = next(
            widget
            for widget in app.screen.query(Static)
            if "LEGACY CONSOLE LIMITATIONS" in str(widget.content)
        )
        _select(warning, "visible warning")
        await pilot.press("ctrl+c")
        assert copied == ["home status", "visible error", "visible warning"]


async def test_diagnostics_log_selection_uses_the_common_copy_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = InputDiagnosticsApp(terminal_profile="windows-terminal")

    async with app.run_test(size=(100, 24)) as pilot:
        copied: list[str] = []
        monkeypatch.setattr(app, "copy_to_clipboard", copied.append)
        log = app.query_one("#diagnostics-log-text", Static)
        _select(log, "diagnostic log")

        await pilot.press("ctrl+c")
        assert copied == ["diagnostic log"]
