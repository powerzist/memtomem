"""Semantic navigation widgets."""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import Static

from memtomem.tui.state import Route


class NavigationItem(Static, can_focus=True):
    """Keyboard and pointer accessible shell route."""

    class Selected(Message):
        def __init__(self, route_id: str) -> None:
            super().__init__()
            self.route_id = route_id

    def __init__(self, route: Route, *, compact: bool = False) -> None:
        self.route = route
        self._compact = compact
        super().__init__(
            self._label(compact),
            id=f"route-{route.id}",
            classes="nav-item",
        )
        self.disabled = not route.available

    def _label(self, compact: bool) -> str:
        label = self.route.short_label if compact else self.route.label
        suffix = "" if self.route.available else "  -"
        return f"  {label}{suffix}"

    def set_compact(self, compact: bool) -> None:
        """Switch labels without replacing route widgets or losing focus."""
        if compact == self._compact:
            return
        self._compact = compact
        self.update(self._label(compact))

    async def _on_click(self, event: events.Click) -> None:
        event.stop()
        synchronize = getattr(self.app, "synchronize_pointer_target", None)
        if synchronize is not None:
            synchronize(self)
        if not self.disabled:
            self.post_message(self.Selected(self.route.id))

    async def _on_key(self, event: events.Key) -> None:
        if event.key != "enter":
            return
        event.stop()
        is_actionable = getattr(self.app, "is_widget_actionable", None)
        if self.disabled or (is_actionable is not None and not is_actionable(self)):
            return
        self.post_message(self.Selected(self.route.id))
