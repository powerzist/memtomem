"""Rendered Help checks for the Phase 4-2 clipboard contract."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from memtomem.tui.styles import load_tui_css
from memtomem.tui.widgets.modals import HelpScreen


class _HelpHarness(App[None]):
    CSS = load_tui_css()

    def compose(self) -> ComposeResult:
        yield Static("background")


def _help_text(screen: HelpScreen) -> str:
    return "\n".join(str(widget.content) for widget in screen.query(Static))


@pytest.mark.parametrize(
    ("width", "height"),
    [(100, 24), (60, 16), (48, 12), (40, 10), (32, 8)],
)
async def test_phase42_help_is_scroll_safe_at_supported_viewports(
    width: int,
    height: int,
) -> None:
    app = _HelpHarness()

    async with app.run_test(size=(width, height)) as pilot:
        app.push_screen(HelpScreen())
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        dialog = screen.query_one(".modal-dialog")
        body = screen.query_one(".modal-body", VerticalScroll)
        text = _help_text(screen)

        assert dialog.region.x >= 0
        assert dialog.region.y >= 0
        assert dialog.region.right <= width
        assert dialog.region.bottom <= height
        assert body.region.width > 0
        assert body.region.height > 0
        assert "Ctrl+C" in text
        assert "editable or read-only" in text
        assert "Ctrl+X" in text
        assert "Ctrl+V" in text
        assert "Hidden, inactive, or modal-background" in text
        assert "MOUSE:TUI" in text
        assert "MOUSE:OS" in text
        assert "hold Shift while dragging" in text
        assert "OSC 52" in text


async def test_phase42_help_preserves_existing_navigation_and_global_contract() -> None:
    app = _HelpHarness()

    async with app.run_test(size=(100, 24)) as pilot:
        app.push_screen(HelpScreen())
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        text = _help_text(screen)

        assert "F2  Navigation" in text
        assert "F3  Main work" in text
        assert "F4  Details" in text
        assert "Arrows or h/j/k/l Move within active panel" in text
        assert "Previous/next panel (no wrap)" in text
        assert "Detail -> Main -> Navigation -> Quit confirmation" in text
