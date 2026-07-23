"""Pure presenters for previews, confirmation, empty states, and errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from memtomem.tui.shared import BorderStyleMixin
from memtomem.tui.terminal import BorderStyle
from memtomem.tui.widgets.controls import ModalButton, TuiInput
from memtomem.tui.widgets.forms import ModalActionBar

PreviewTone = Literal["default", "muted", "ok", "warning", "error"]
ConfirmTone = Literal["primary", "destructive"]
_PREVIEW_TONES: frozenset[str] = frozenset({"default", "muted", "ok", "warning", "error"})
_NOTICE_MARKERS: dict[PreviewTone, str] = {
    "default": "[i]",
    "muted": "[-]",
    "ok": "[+]",
    "warning": "[!]",
    "error": "[x]",
}


def _with_semantic_class(semantic_class: str, classes: str | None) -> str:
    return f"{semantic_class} {classes or ''}".strip()


@dataclass(frozen=True)
class PreviewItem:
    """One literal label/value pair in a domain-supplied preview."""

    label: str
    value: str
    tone: PreviewTone = "default"

    def __post_init__(self) -> None:
        if self.tone not in _PREVIEW_TONES:
            raise ValueError(f"unsupported preview tone: {self.tone}")


@dataclass(frozen=True)
class PreviewPresentation:
    """Immutable data needed to present a preview without executing it."""

    title: str
    summary: str
    fingerprint: str
    items: tuple[PreviewItem, ...] = ()

    def __post_init__(self) -> None:
        if not self.fingerprint:
            raise ValueError("preview fingerprint must not be empty")


class PreviewBlock(Vertical):
    """Consequence-first preview with literal dynamic values."""

    def __init__(
        self,
        preview: PreviewPresentation,
        *,
        show_title: bool = True,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            classes=_with_semantic_class("preview-block", classes),
            disabled=disabled,
        )
        self.preview = preview
        self.show_title = show_title

    def compose(self) -> ComposeResult:
        if self.show_title:
            yield Static(f"[ {self.preview.title} ]", classes="preview-title", markup=False)
        yield Static(self.preview.summary, classes="preview-summary", markup=False)
        for item in self.preview.items:
            tone_class = "" if item.tone == "default" else f" {item.tone}"
            with Horizontal(classes="preview-item"):
                yield Static(item.label, classes="preview-item-label", markup=False)
                yield Static(
                    item.value,
                    classes=f"preview-item-value{tone_class}",
                    markup=False,
                )


class EmptyState(Vertical):
    """Explicit empty result that communicates with text, not color alone."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            classes=_with_semantic_class("empty-state", classes),
            disabled=disabled,
        )
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        yield Static(f"[ {self.title} ]", classes="empty-state-title", markup=False)
        yield Static(self.message, classes="empty-state-message", markup=False)


class ErrorState(Vertical):
    """User-safe structured error presentation without diagnostic details."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        recovery: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            classes=_with_semantic_class("error-state", classes),
            disabled=disabled,
        )
        self.code = code
        self.message = message
        self.recovery = recovery

    def compose(self) -> ComposeResult:
        yield Static(f"[ ERROR {self.code} ]", classes="error-state-title", markup=False)
        yield Static(self.message, classes="error-state-message", markup=False)
        if self.recovery is not None:
            yield Static(self.recovery, classes="error-state-recovery", markup=False)


class NoticeBlock(Vertical):
    """Reusable text-first notice for disclosure, warning, and success states."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        tone: PreviewTone = "default",
        recovery: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        if tone not in _PREVIEW_TONES:
            raise ValueError(f"unsupported notice tone: {tone}")
        super().__init__(
            name=name,
            id=id,
            classes=_with_semantic_class(f"notice-block notice-{tone}", classes),
            disabled=disabled,
        )
        self.title = title
        self.message = message
        self.tone = tone
        self.recovery = recovery

    def compose(self) -> ComposeResult:
        yield Static(
            f"{_NOTICE_MARKERS[self.tone]} {self.title}",
            classes="notice-title",
            markup=False,
        )
        yield Static(self.message, classes="notice-message", markup=False)
        if self.recovery is not None:
            yield Static(self.recovery, classes="notice-recovery", markup=False)

    def update_notice(
        self,
        title: str,
        message: str,
        *,
        tone: PreviewTone | None = None,
    ) -> None:
        """Update a stable inline notice while preserving surrounding form state."""
        resolved_tone = self.tone if tone is None else tone
        if resolved_tone not in _PREVIEW_TONES:
            raise ValueError(f"unsupported notice tone: {resolved_tone}")
        for candidate in _PREVIEW_TONES:
            self.set_class(candidate == resolved_tone, f"notice-{candidate}")
        self.title = title
        self.message = message
        self.tone = resolved_tone
        if self.is_mounted:
            self.query_one(".notice-title", Static).update(
                f"{_NOTICE_MARKERS[resolved_tone]} {title}"
            )
            self.query_one(".notice-message", Static).update(message)


class ConfirmationBlock(Vertical):
    """Present fingerprint validity and optional exact-text confirmation."""

    INPUT_ID = "confirmation-input"

    def __init__(
        self,
        *,
        preview_fingerprint: str,
        current_fingerprint: str,
        typed_confirmation: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        if typed_confirmation == "":
            raise ValueError("typed confirmation text must not be empty")
        super().__init__(
            name=name,
            id=id,
            classes=_with_semantic_class("confirmation-block", classes),
            disabled=disabled,
        )
        self.preview_fingerprint = preview_fingerprint
        self.current_fingerprint = current_fingerprint
        self.typed_confirmation = typed_confirmation
        self.add_class(
            "fingerprint-mismatch" if self.fingerprint_mismatch else "fingerprint-verified"
        )

    @property
    def fingerprint_mismatch(self) -> bool:
        return self.preview_fingerprint != self.current_fingerprint

    def compose(self) -> ComposeResult:
        if self.fingerprint_mismatch:
            yield Static("[ STATE CHANGED ]", classes="confirmation-status", markup=False)
            yield Static(
                "The current state no longer matches this preview. Create and review a fresh "
                "preview before applying.",
                classes="confirmation-message",
                markup=False,
            )
            yield self._fingerprint_row("Preview fingerprint", self.preview_fingerprint)
            yield self._fingerprint_row("Current fingerprint", self.current_fingerprint)
        else:
            yield Static("[ STATE VERIFIED ]", classes="confirmation-status", markup=False)
            yield Static(
                "The current state matches this preview.",
                classes="confirmation-message",
                markup=False,
            )

        if self.typed_confirmation is not None:
            yield Static(
                "Type the exact text below, then review the Apply button.",
                classes="confirmation-instruction",
                markup=False,
            )
            yield Static(
                self.typed_confirmation,
                classes="confirmation-phrase",
                markup=False,
            )
            yield TuiInput(
                placeholder="Exact confirmation text",
                id=self.INPUT_ID,
                classes="text-input confirmation-input",
                disabled=self.fingerprint_mismatch,
            )

    @staticmethod
    def _fingerprint_row(label: str, value: str) -> Horizontal:
        return Horizontal(
            Static(label, classes="fingerprint-label", markup=False),
            Static(value, classes="fingerprint-value", markup=False),
            classes="fingerprint-row",
        )


class PreviewConfirmScreen(BorderStyleMixin, ModalScreen[bool]):
    """Keyboard-first presenter that returns intent but performs no domain action."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("left", "focus_confirm", "Apply", show=False),
        Binding("right", "focus_cancel", "Cancel", show=False),
    ]

    CONFIRM_ID = "preview-confirm-apply"
    CANCEL_ID = "preview-confirm-cancel"
    BLOCK_ID = "preview-confirmation-block"

    def __init__(
        self,
        preview: PreviewPresentation,
        *,
        current_fingerprint: str,
        typed_confirmation: str | None = None,
        confirm_label: str = "APPLY",
        confirm_tone: ConfirmTone = "primary",
        border_style: BorderStyle = "solid",
    ) -> None:
        if confirm_tone not in {"primary", "destructive"}:
            raise ValueError(f"unsupported confirm tone: {confirm_tone}")
        if not confirm_label:
            raise ValueError("confirm label must not be empty")
        if typed_confirmation == "":
            raise ValueError("typed confirmation text must not be empty")
        super().__init__()
        self.preview = preview
        self.current_fingerprint = current_fingerprint
        self.typed_confirmation = typed_confirmation
        self.confirm_label = confirm_label
        self.confirm_tone = confirm_tone
        self.border_style = border_style

    @property
    def fingerprint_mismatch(self) -> bool:
        return self.preview.fingerprint != self.current_fingerprint

    @property
    def can_confirm(self) -> bool:
        if self.fingerprint_mismatch:
            return False
        if self.typed_confirmation is None:
            return True
        if not self.is_mounted:
            return False
        field = self.query_one(f"#{ConfirmationBlock.INPUT_ID}", TuiInput)
        return field.value == self.typed_confirmation

    def compose(self) -> ComposeResult:
        with Vertical(classes=f"modal-dialog preview-confirm-dialog {self.border_class}".strip()):
            yield Static(
                f"[ {self.preview.title} ]",
                classes="modal-title",
                markup=False,
            )
            if self.fingerprint_mismatch:
                yield Static(
                    "[ STATE CHANGED ]",
                    classes="modal-status confirmation-status error",
                    markup=False,
                )
            with VerticalScroll(classes="modal-body preview-confirm-body"):
                preview_block = PreviewBlock(
                    self.preview,
                    show_title=False,
                    classes=self.border_class,
                )
                confirmation_block = ConfirmationBlock(
                    preview_fingerprint=self.preview.fingerprint,
                    current_fingerprint=self.current_fingerprint,
                    typed_confirmation=self.typed_confirmation,
                    id=self.BLOCK_ID,
                    classes=self.border_class,
                )
                if self.fingerprint_mismatch:
                    yield confirmation_block
                    yield preview_block
                else:
                    yield preview_block
                    yield confirmation_block
            confirm_color = "red" if self.confirm_tone == "destructive" else "cyan"
            yield ModalActionBar(
                ModalButton(
                    Text(f"[ {self.confirm_label} ]"),
                    id=self.CONFIRM_ID,
                    classes=f"action-button {confirm_color}",
                ),
                ModalButton(
                    Text("[ CANCEL ]"),
                    id=self.CANCEL_ID,
                    classes="action-button",
                ),
            )

    def on_mount(self) -> None:
        self._apply_compact_layout()
        self._sync_confirmation_state()
        self.query_one(f"#{self.CANCEL_ID}", ModalButton).focus()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_compact_layout(event.size.width, event.size.height)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == ConfirmationBlock.INPUT_ID:
            self._sync_confirmation_state()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == ConfirmationBlock.INPUT_ID and self.can_confirm:
            self.query_one(f"#{self.CONFIRM_ID}", ModalButton).focus()

    def on_button_pressed(self, event: ModalButton.Pressed) -> None:
        if event.button.id == self.CONFIRM_ID:
            if self.can_confirm:
                self.dismiss(True)
            return
        if event.button.id == self.CANCEL_ID:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_focus_confirm(self) -> None:
        button = self.query_one(f"#{self.CONFIRM_ID}", ModalButton)
        if not button.disabled:
            button.focus()

    def action_focus_cancel(self) -> None:
        self.query_one(f"#{self.CANCEL_ID}", ModalButton).focus()

    def _sync_confirmation_state(self) -> None:
        can_confirm = self.can_confirm
        button = self.query_one(f"#{self.CONFIRM_ID}", ModalButton)
        button.disabled = not can_confirm
        block = self.query_one(f"#{self.BLOCK_ID}", ConfirmationBlock)
        block.set_class(can_confirm, "confirmation-valid")
        block.set_class(
            not can_confirm and not self.fingerprint_mismatch,
            "confirmation-incomplete",
        )

    def _apply_compact_layout(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        viewport_width = self.size.width if width is None else width
        viewport_height = self.size.height if height is None else height
        self.set_class(
            viewport_width < 48 or viewport_height < 14,
            "preview-confirm-compact",
        )
