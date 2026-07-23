"""Functional control boundaries shared by shell screens."""

from __future__ import annotations

from typing import Any

from textual import events
from textual.actions import SkipAction
from textual.binding import Binding
from textual.dom import NoScreen
from textual.widgets import Button, Input


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
    """Single-line editor routed through the app's common clipboard boundary."""

    BINDINGS = [
        Binding("ctrl+c", "copy", "Copy", show=False),
        Binding("ctrl+x", "cut", "Cut", show=False),
        Binding(
            "ctrl+v,ctrl+shift+v,shift+insert",
            "paste",
            "Paste",
            show=False,
        ),
    ]

    def action_copy(self) -> None:
        if not self._is_clipboard_target_active() or not self.selected_text:
            raise SkipAction()
        self.app.copy_to_clipboard(self.selected_text)

    def action_cut(self) -> None:
        if not self._is_clipboard_target_active() or not self.selected_text:
            return
        self.app.copy_to_clipboard(self.selected_text)
        self.delete_selection()

    def action_paste(self) -> None:
        if not self._is_clipboard_target_active():
            return
        value = self.app.clipboard
        lines = value.splitlines()
        first_line = lines[0] if lines else value
        self.replace(first_line, *self.selection)

    def _on_paste(self, event: events.Paste) -> None:
        if not self._is_clipboard_target_active():
            event.stop()
            event.prevent_default()
            return
        super()._on_paste(event)
        # Textual dispatches convention handlers across the MRO. Mark this event
        # handled so Input._on_paste is not invoked a second time automatically.
        event.prevent_default()

    def _is_clipboard_target_active(self) -> bool:
        validator = getattr(self.app, "is_clipboard_target_active", None)
        if validator is not None:
            return bool(validator(self))

        try:
            widget_screen = self.screen
        except (NoScreen, RuntimeError):
            return False
        if (
            widget_screen is not self.app.screen
            or self.app.focused is not self
            or self.disabled
            or not self.is_attached
        ):
            return False
        current: Any = self
        while current is not None:
            if not current.display or not current.visible:
                return False
            current = getattr(current, "parent", None)
        return True
