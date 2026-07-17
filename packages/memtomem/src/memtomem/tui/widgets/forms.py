"""Reusable, domain-neutral form and action layouts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static

from memtomem.tui.widgets.controls import ModalButton, PanelButton


def _with_semantic_class(semantic_class: str, classes: str | None) -> str:
    return f"{semantic_class} {classes or ''}".strip()


class FormRow(Vertical):
    """Present a literal label, control, and optional supporting messages."""

    def __init__(
        self,
        label: str,
        control: Widget,
        *,
        supporting_text: str | None = None,
        error: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            classes=_with_semantic_class("form-row", classes),
            disabled=disabled,
        )
        self.label = label
        self.control = control
        self.supporting_text = supporting_text
        self.error = error

    def compose(self) -> ComposeResult:
        with Horizontal(classes="form-row-line"):
            yield Static(self.label, classes="form-label", markup=False)
            with Vertical(classes="form-control"):
                yield self.control
        if self.supporting_text is not None:
            yield Static(
                self.supporting_text,
                classes="form-message form-support muted",
                markup=False,
            )
        if self.error is not None:
            yield Static(self.error, classes="form-message form-error", markup=False)


class ActionBar(Horizontal):
    """Panel action row whose controls obey shell pointer/focus policy."""

    def __init__(
        self,
        *actions: PanelButton,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        if not all(isinstance(action, PanelButton) for action in actions):
            raise TypeError("ActionBar accepts PanelButton controls only")
        super().__init__(
            *actions,
            name=name,
            id=id,
            classes=_with_semantic_class("action-bar", classes),
            disabled=disabled,
        )


class ModalActionBar(Horizontal):
    """Modal action row whose controls stay inside the modal boundary."""

    def __init__(
        self,
        *actions: ModalButton,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        if not all(isinstance(action, ModalButton) for action in actions):
            raise TypeError("ModalActionBar accepts ModalButton controls only")
        super().__init__(
            *actions,
            name=name,
            id=id,
            classes=_with_semantic_class("action-bar modal-actions", classes),
            disabled=disabled,
        )
