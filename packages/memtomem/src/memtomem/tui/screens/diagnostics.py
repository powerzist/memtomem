"""Standalone input diagnostics kept independent from the main shell."""

from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from memtomem.tui.shared import BorderStyleMixin, PanelScroll
from memtomem.tui.styles import load_tui_css
from memtomem.tui.terminal import BorderStyle, detect_terminal_profile, has_ime_limitations
from memtomem.tui.widgets.controls import TuiInput


class DiagnosticInput(TuiInput):
    """Input that reports the raw key and paste events it receives."""

    async def _on_key(self, event: events.Key) -> None:
        value_before = self.value
        await super()._on_key(event)
        recorder = getattr(self.app, "record_key_event", None)
        if recorder is not None:
            recorder(event, value_before)

    def _on_paste(self, event: events.Paste) -> None:
        value_before = self.value
        super()._on_paste(event)
        event.prevent_default()
        recorder = getattr(self.app, "record_paste_event", None)
        if recorder is not None:
            recorder(event, value_before)


class InputDiagnosticsApp(BorderStyleMixin, App[None]):
    """Small isolated surface for inspecting terminal input events."""

    CSS = load_tui_css()
    BINDINGS = [Binding("escape,ctrl+q", "quit", "Quit")]

    def __init__(
        self,
        *,
        border_style: BorderStyle = "solid",
        terminal_profile: str | None = None,
        mouse_enabled: bool = True,
    ) -> None:
        super().__init__()
        self.border_style = border_style
        self.terminal_profile = terminal_profile or detect_terminal_profile()
        self.mouse_enabled = mouse_enabled
        self.input_events: list[str] = []
        self.input_event_count = 0

    def compose(self) -> ComposeResult:
        with Vertical(
            id="diagnostics",
            classes=f"section-panel diagnostic-screen {self.border_class}".strip(),
        ):
            yield Static("[ INPUT DIAGNOSTICS ]", classes="section-title")
            yield Static(f"Terminal profile: {self.terminal_profile}", classes="muted")
            if has_ime_limitations(self.terminal_profile):
                yield Static(
                    "Korean IME input is limited in legacy Windows consoles. "
                    "Use Windows Terminal for Korean text input.",
                    classes="warning",
                )
            yield Static(
                "Type Korean/CJK text or paste in the field below. Raw key and paste events "
                "appear in the log. Press Esc or Ctrl+Q to exit.",
                classes="supporting-text",
            )
            yield DiagnosticInput(
                placeholder="Type here...",
                id="diagnostics-input",
                classes="text-input diagnostic-input",
            )
            yield Static(
                "Current value: ''",
                id="diagnostics-value",
                classes="muted",
                markup=False,
            )
            with PanelScroll(id="diagnostics-log", classes="diagnostic-log") as log:
                log.styles.height = "1fr"
                yield Static(
                    "Waiting for key or paste events...",
                    id="diagnostics-log-text",
                    markup=False,
                )

    def on_mount(self) -> None:
        self.query_one("#diagnostics-input", DiagnosticInput).focus()

    def record_key_event(self, event: events.Key, value_before: str) -> None:
        self._append_input_event(
            "key",
            [
                f"key={event.key!r}",
                f"character={event.character!r}",
                f"printable={event.is_printable}",
                f"value_before={value_before!r}",
            ],
        )

    def record_paste_event(self, event: events.Paste, value_before: str) -> None:
        self._append_input_event(
            "paste",
            [
                f"text={event.text!r}",
                f"value_before={value_before!r}",
            ],
        )

    def _append_input_event(self, event_type: str, fields: list[str]) -> None:
        self.input_event_count += 1
        self.input_events.append(f"{self.input_event_count:03d} {event_type}: " + "  ".join(fields))
        del self.input_events[:-40]
        self.query_one("#diagnostics-log-text", Static).update("\n".join(self.input_events))
        value = self.query_one("#diagnostics-input", DiagnosticInput).value
        self.query_one("#diagnostics-value", Static).update(f"Current value: {value!r}")
        log = self.query_one("#diagnostics-log", PanelScroll)
        log.call_after_refresh(log.scroll_end, animate=False, force=True)
