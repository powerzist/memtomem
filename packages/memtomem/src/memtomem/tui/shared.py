"""Shared Textual UI primitives."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll

from memtomem.tui.terminal import BorderStyle


COMMON_PANEL_CSS = """
Button {
    margin-top: 1;
    margin-right: 1;
}

Button.active-nav {
    background: #123447;
    color: #ffffff;
    text-style: bold;
}

Button.tui-secondary {
    background: #123447;
    color: #ffffff;
}

.title {
    color: #45e0ff;
    text-style: bold;
    margin-bottom: 1;
}

.muted {
    color: #8b9aad;
}

.warning {
    color: #ffd166;
    text-style: bold;
}

.ok {
    color: #4ade80;
    text-style: bold;
}

.error {
    color: #ff6b6b;
    text-style: bold;
}
"""


class BorderStyleMixin:
    """Mixin for widgets/screens that render solid or ASCII borders."""

    border_style: BorderStyle

    @property
    def border_class(self) -> str:
        return "ascii-border" if self.border_style == "ascii" else ""


class PanelScroll(VerticalScroll):
    """Scrollable panel body that leaves arrow-key navigation to its owner."""

    BINDINGS = [
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
    ]

    def action_scroll_up(self) -> None:
        self._call_owner_action("action_item_previous")

    def action_scroll_down(self) -> None:
        self._call_owner_action("action_item_next")

    def action_scroll_left(self) -> None:
        self._call_owner_action("action_panel_previous")

    def action_scroll_right(self) -> None:
        self._call_owner_action("action_panel_next")

    def _call_owner_action(self, action_name: str) -> None:
        handler = getattr(self.screen, action_name, None) or getattr(self.app, action_name, None)
        if handler is not None:
            handler()
