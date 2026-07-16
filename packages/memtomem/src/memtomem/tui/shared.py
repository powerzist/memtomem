"""Shared Textual UI primitives."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll

from memtomem.tui.terminal import BorderStyle


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
        self._call_owner_action("action_item_left")

    def action_scroll_right(self) -> None:
        self._call_owner_action("action_item_right")

    def _call_owner_action(self, action_name: str) -> None:
        handler = getattr(self.screen, action_name, None) or getattr(self.app, action_name, None)
        if handler is not None:
            handler()
