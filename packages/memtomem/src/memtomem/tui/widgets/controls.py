"""Functional control boundaries shared by shell screens."""

from __future__ import annotations

from textual import events
from textual.widgets import Button, Input

from memtomem.tui.clipboard import read_os_clipboard, write_os_clipboard


class PanelButton(Button):
    """Button that synchronizes its containing shell section on mouse input."""

    async def _on_click(self, event: events.Click) -> None:
        event.stop()
        event.prevent_default()
        synchronize = getattr(self.app, "synchronize_pointer_target", None)
        if synchronize is not None:
            synchronize(self)
        if not self.has_class("-active"):
            self.press()

    def action_press(self) -> None:
        """Reject keyboard activation from remembered focus in an inactive section."""
        is_actionable = getattr(self.app, "is_widget_actionable", None)
        if is_actionable is not None and not is_actionable(self):
            return
        super().action_press()


class ModalButton(Button):
    """Explicit modal control boundary."""


class TuiInput(Input):
    """Input with best-effort OS clipboard behavior."""

    BINDINGS = [
        ("ctrl+c", "copy", "Copy"),
        ("ctrl+x", "cut", "Cut"),
        ("ctrl+v,ctrl+shift+v,shift+insert", "paste", "Paste"),
    ]

    def action_copy(self) -> None:
        start, end = sorted((self.selection.start, self.selection.end))
        if start == end:
            return
        write_os_clipboard(self.value[start:end])

    def action_cut(self) -> None:
        start, end = sorted((self.selection.start, self.selection.end))
        if start == end or not write_os_clipboard(self.value[start:end]):
            return
        self.value = self.value[:start] + self.value[end:]
        self.cursor_position = start

    def action_paste(self) -> None:
        value = read_os_clipboard()
        if value is None:
            return
        start, end = sorted((self.selection.start, self.selection.end))
        self.value = self.value[:start] + value + self.value[end:]
        self.cursor_position = start + len(value)
