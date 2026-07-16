"""Shared modal family for Help, warnings, and confirmation."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from memtomem.tui.shared import BorderStyleMixin
from memtomem.tui.terminal import BorderStyle
from memtomem.tui.widgets.controls import ModalButton


class HelpScreen(BorderStyleMixin, ModalScreen[None]):
    BINDINGS = [Binding("escape,question_mark", "close", "Close", show=False)]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        with Vertical(classes=f"modal-dialog help-dialog {self.border_class}".strip()):
            yield Static("[ KEYBOARD HELP ]", classes="modal-title")
            with VerticalScroll(classes="modal-body"):
                yield Static(
                    "SECTIONS\n"
                    "  F2  Navigation    F3  Main work    F4  Details\n\n"
                    "NAVIGATION\n"
                    "  Arrows or h/j/k/l Move within active panel\n"
                    r"  \[ / ]            Previous/next panel (no wrap)"
                    "\n"
                    "  PageUp/PageDown   Page active pane\n"
                    "  F7/F8             Previous/next active-panel tab\n\n"
                    "GLOBAL\n"
                    "  Esc               Detail -> Main -> Navigation -> Quit confirmation\n"
                    "  F6 or Alt+M       Toggle mouse mode\n"
                    "  Ctrl+R            Refresh\n"
                    "  ?                 Help\n"
                    "  Ctrl+Q            Quit confirmation"
                )
            with Horizontal(classes="modal-actions"):
                yield ModalButton(r"\[ CLOSE ]", id="help-close", classes="action-button cyan")

    def on_button_pressed(self, event: ModalButton.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


KeybindingsScreen = HelpScreen


class QuitConfirmScreen(BorderStyleMixin, ModalScreen[bool]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("left,h,up,k", "focus_yes", "Yes", show=False),
        Binding("right,l,down,j", "focus_no", "No", show=False),
    ]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        with Vertical(classes=f"modal-dialog confirmation-dialog {self.border_class}".strip()):
            yield Static("[ QUIT MEMTOMEM? ]", classes="modal-title")
            yield Static("Active UI state will be discarded.", classes="modal-body")
            with Horizontal(classes="modal-actions"):
                yield ModalButton(r"\[ YES ]", id="quit-yes", classes="choice-button red")
                yield ModalButton(r"\[ NO ]", id="quit-no", classes="choice-button cyan")

    def on_mount(self) -> None:
        self.query_one("#quit-no", ModalButton).focus()

    def on_button_pressed(self, event: ModalButton.Pressed) -> None:
        self.dismiss(event.button.id == "quit-yes")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_focus_yes(self) -> None:
        self.query_one("#quit-yes", ModalButton).focus()

    def action_focus_no(self) -> None:
        self.query_one("#quit-no", ModalButton).focus()


class ConhostWarningScreen(BorderStyleMixin, ModalScreen[None]):
    BINDINGS = [Binding("escape,enter", "close", "Close", show=False)]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        with Vertical(classes=f"modal-dialog warning-dialog {self.border_class}".strip()):
            yield Static("[ LEGACY CONSOLE LIMITATIONS ]", classes="modal-title warning")
            yield Static(
                "IME input, mouse text selection, and clipboard behavior may be limited.\n"
                "Every action remains available from the keyboard.",
                classes="modal-body",
            )
            with Horizontal(classes="modal-actions"):
                yield ModalButton(
                    r"\[ CONTINUE ]",
                    id="warning-close",
                    classes="action-button yellow",
                )

    def on_button_pressed(self, event: ModalButton.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
