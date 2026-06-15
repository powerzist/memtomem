"""Textual application entry point for ``mm tui``."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import events
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, ListItem, ListView, Static

from memtomem.tui.catalog import COMMAND_CATALOG
from memtomem.tui.clipboard import read_os_clipboard, write_os_clipboard
from memtomem.tui.runtime import Readiness, ReadinessState, config_exists, inspect_readiness
from memtomem.tui.shared import COMMON_PANEL_CSS, BorderStyleMixin, PanelScroll
from memtomem.tui.terminal import BorderStyle, detect_terminal_profile, has_ime_limitations

if TYPE_CHECKING:
    from memtomem.models import SearchResult


class KeybindingsScreen(BorderStyleMixin, ModalScreen[None]):
    """Modal help screen for keyboard shortcuts."""

    CSS = """
    KeybindingsScreen {
        align: center middle;
    }

    #keybindings-dialog {
        width: 74;
        max-width: 90%;
        max-height: 90%;
        border: solid #45e0ff;
        background: #0d141c;
        padding: 1 2;
    }

    #keybindings-title {
        color: #45e0ff;
        text-style: bold;
        margin-bottom: 1;
    }

    #keybindings-body {
        margin-bottom: 1;
    }

    #keybindings-body-scroll {
        height: 1fr;
        overflow-y: auto;
        margin-bottom: 1;
    }

    #keybindings-dialog.ascii-border {
        border: ascii #45e0ff;
    }
    """ + COMMON_PANEL_CSS

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("up,j", "item_previous", "Previous item", show=False),
        Binding("down,k", "item_next", "Next item", show=False),
        Binding("page_up", "page_up", "Page up", show=False),
        Binding("page_down", "page_down", "Page down", show=False),
    ]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        body = "\n".join(
            [
                "Navigation",
                "  Up/j            Move up within the current panel",
                "  Down/k          Move down within the current panel",
                "  PgUp/PgDn       Scroll the current panel by one page",
                "  Left/Right, h/l Move focus between panels",
                "  Tab/Shift+Tab   Move focus between controls",
                "  Enter           Activate the focused control",
                "  Esc             Close modal / cancel current overlay",
                "",
                "Global",
                "  Ctrl+K          Open command catalog",
                "  F6              Toggle mouse mode",
                "  Alt+M           Toggle mouse mode",
                "  r               Refresh",
                "  ?               Show this keymap",
                "  q               Quit",
                "",
                "Clipboard",
                "  Ctrl+C          Copy",
                "  Ctrl+X          Cut",
                "  Ctrl+V          Paste",
                "  Ctrl+Shift+V    Paste",
                "  Shift+Insert    Paste",
            ]
        )
        dialog_classes = "ascii-border" if self.border_style == "ascii" else ""
        with Vertical(id="keybindings-dialog", classes=dialog_classes):
            yield Static("Keyboard shortcuts", id="keybindings-title")
            with PanelScroll(id="keybindings-body-scroll"):
                yield Static(body, id="keybindings-body")
            yield Button("Close", id="close-keybindings", classes="tui-secondary")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-keybindings":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_page_up(self) -> None:
        self.query_one("#keybindings-body-scroll", PanelScroll).scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one("#keybindings-body-scroll", PanelScroll).scroll_page_down(animate=False)

    def action_item_previous(self) -> None:
        self.query_one("#close-keybindings", Button).focus()

    def action_item_next(self) -> None:
        self.query_one("#close-keybindings", Button).focus()


class ConhostWarningScreen(BorderStyleMixin, ModalScreen[None]):
    """Startup warning for legacy Windows console hosts."""

    CSS = """
    ConhostWarningScreen {
        align: center middle;
    }

    #conhost-warning-dialog {
        width: 76;
        max-width: 90%;
        max-height: 90%;
        border: solid #f2c94c;
        background: #0d141c;
        padding: 1 2;
    }

    #conhost-warning-title {
        color: #f2c94c;
        text-style: bold;
        margin-bottom: 1;
    }

    #conhost-warning-body {
        margin-bottom: 1;
    }

    #conhost-warning-dialog.ascii-border {
        border: ascii #f2c94c;
    }
    """ + COMMON_PANEL_CSS

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close", show=False),
    ]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        dialog_classes = "ascii-border" if self.border_style == "ascii" else ""
        body = (
            "Legacy Windows console hosts are not fully supported by the TUI.\n\n"
            "Known limitations include Korean IME input, mouse text selection, and "
            "some clipboard behavior. Windows Terminal is strongly recommended."
        )
        with Vertical(id="conhost-warning-dialog", classes=dialog_classes):
            yield Static("Windows Terminal strongly recommended", id="conhost-warning-title")
            yield Static(body, id="conhost-warning-body")
            yield Button("Continue", id="close-conhost-warning", classes="tui-secondary")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-conhost-warning":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class TuiInput(Input):
    """Input widget that uses the OS clipboard when possible."""

    BINDINGS = [
        *Input.BINDINGS,
        Binding("ctrl+shift+v,shift+insert", "paste", "Paste text", show=False),
    ]

    async def _on_key(self, event: events.Key) -> None:
        if event.key in {"f6", "alt+m"}:
            event.stop()
            event.prevent_default()
            toggle = getattr(self.app, "action_toggle_mouse_mode", None)
            if toggle is not None:
                toggle()
            return
        await super()._on_key(event)

    def action_copy(self) -> None:
        selected_text = self.selected_text
        if not selected_text:
            raise SkipAction()
        self.app.copy_to_clipboard(selected_text)
        write_os_clipboard(selected_text)

    def action_cut(self) -> None:
        selected_text = self.selected_text
        if not selected_text:
            raise SkipAction()
        self.app.copy_to_clipboard(selected_text)
        write_os_clipboard(selected_text)
        self.delete_selection()

    def action_paste(self) -> None:
        clipboard = read_os_clipboard()
        if clipboard is None:
            clipboard = self.app.clipboard
        start, end = self.selection
        self.replace(clipboard.splitlines()[0] if clipboard else "", start, end)


class DiagnosticInput(TuiInput):
    """Input widget that records the raw key events it receives."""

    async def _on_key(self, event: events.Key) -> None:
        recorder = getattr(self.app, "record_key_event", None)
        if recorder is not None:
            recorder(event, self.value)
        await super()._on_key(event)

    def _on_paste(self, event: events.Paste) -> None:
        recorder = getattr(self.app, "record_paste_event", None)
        if recorder is not None:
            recorder(event, self.value)
        super()._on_paste(event)


class InputDiagnosticsApp(BorderStyleMixin, App[None]):
    """Small Textual app for inspecting terminal input events."""

    CSS = """
    Screen {
        background: #0d141c;
        color: #d8dee9;
    }

    #diagnostics {
        height: 1fr;
        padding: 1;
    }

    #diagnostics-title {
        color: #45e0ff;
        text-style: bold;
        margin-bottom: 1;
    }

    #diagnostics-input {
        margin: 1 0;
    }

    #diagnostics-log {
        height: 1fr;
        border: solid #1d2a37;
        padding: 1;
    }

    #diagnostics-log.ascii-border {
        border: ascii #1d2a37;
    }
    """ + COMMON_PANEL_CSS

    BINDINGS = [
        Binding("escape,ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        border_style: BorderStyle = "solid",
        terminal_profile: str | None = None,
    ) -> None:
        super().__init__()
        self.border_style = border_style
        self.terminal_profile = terminal_profile or detect_terminal_profile()
        self.input_events: list[str] = []

    def compose(self) -> ComposeResult:
        log_classes = "ascii-border" if self.border_style == "ascii" else ""
        with Vertical(id="diagnostics"):
            yield Static("memtomem TUI Input Diagnostics", id="diagnostics-title")
            if has_ime_limitations(self.terminal_profile):
                yield Static(
                    "Korean IME input is limited in legacy Windows consoles. "
                    "Use Windows Terminal for Korean text input.",
                    classes="warning",
                )
            yield Static(
                "Type Korean text in the field below. Press Escape or Ctrl+Q to quit.",
                classes="muted",
            )
            yield DiagnosticInput(placeholder="Type here...", id="diagnostics-input")
            yield Static("", id="diagnostics-value")
            with PanelScroll(id="diagnostics-log", classes=log_classes):
                yield Static("Waiting for key events...", id="diagnostics-log-text")
        yield Footer()

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
        self.input_events.append(f"{len(self.input_events) + 1:03d} {event_type}: " + "  ".join(fields))
        del self.input_events[:-40]
        self.query_one("#diagnostics-log-text", Static).update("\n".join(self.input_events))
        value = self.query_one("#diagnostics-input", DiagnosticInput).value
        self.query_one("#diagnostics-value", Static).update(f"Current value: {value!r}")


class MemtomemTuiApp(BorderStyleMixin, App[None]):
    """Initial Textual shell for memtomem.

    The app starts with readiness routing:

    * no config -> setup screen
    * configured but empty index with files -> index-required screen
    * ready -> dashboard
    """

    CSS = """
    Screen {
        background: #0d141c;
        color: #d8dee9;
    }

    #root {
        height: 100%;
        padding: 1 2;
    }

    #topbar {
        height: 1;
        layout: horizontal;
        margin: 0 1 1 1;
    }

    #top-title {
        width: 1fr;
        color: #45e0ff;
        text-style: bold;
    }

    #top-clock {
        width: 10;
        content-align: right middle;
        color: #8b9aad;
        margin-right: 1;
    }

    #layout {
        height: 1fr;
    }

    #nav {
        width: 24;
        min-width: 18;
        border: solid #233242;
        margin-right: 1;
        padding: 1;
    }

    #nav-body {
        height: 1fr;
        overflow-y: auto;
    }

    #main {
        width: 1fr;
        border: solid #233242;
        margin-right: 1;
        padding: 1 2;
    }

    #main-body {
        height: 1fr;
        overflow-y: auto;
        padding-right: 1;
    }

    #detail {
        width: 34;
        border: solid #233242;
        padding: 1;
    }

    #detail-body {
        height: 1fr;
        overflow-y: auto;
        padding-right: 1;
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

    #nav.active-panel,
    #main.active-panel,
    #detail.active-panel {
        border: solid #45e0ff;
    }

    #nav.ascii-border,
    #main.ascii-border,
    #detail.ascii-border {
        border: ascii #233242;
    }

    #nav.ascii-border.active-panel,
    #main.ascii-border.active-panel,
    #detail.ascii-border.active-panel {
        border: ascii #45e0ff;
    }

    #index-log {
        height: 1fr;
        margin-top: 1;
        border: solid #1d2a37;
        padding: 1;
    }

    #search-query {
        margin-bottom: 1;
    }

    #search-results {
        height: 1fr;
        margin-top: 1;
    }

    #mouse-status {
        width: 12;
        content-align: right middle;
        color: #8b9aad;
        margin-right: 1;
    }
    """ + COMMON_PANEL_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("ctrl+k", "show_catalog", "Commands"),
        Binding("?", "show_keybindings", "Help"),
        Binding("up,j", "item_previous", "Previous item", show=False),
        Binding("down,k", "item_next", "Next item", show=False),
        Binding("page_up", "page_up", "Page up", show=False),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("page_down", "page_down", "Page down", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
        Binding("left,h", "panel_previous", "Previous panel", show=False),
        Binding("right,l", "panel_next", "Next panel", show=False),
        Binding("f6,alt+m", "toggle_mouse_mode", "Mouse mode", show=False),
        Binding("enter", "nav_activate", "Open menu", show=False),
    ]

    NAV_BUTTON_IDS = ("nav-dashboard", "nav-search", "nav-commands", "nav-refresh", "nav-help")
    PANEL_IDS = ("nav", "main", "detail")

    def __init__(
        self,
        *,
        border_style: BorderStyle = "solid",
        startup_refresh: bool = True,
        terminal_profile: str | None = None,
        mouse_enabled: bool = True,
    ) -> None:
        super().__init__()
        self._components_cm: AbstractAsyncContextManager[Any] | None = None
        self.comp: Any | None = None
        self.readiness: Readiness | None = None
        self.compact = False
        self.startup_refresh = startup_refresh
        self.nav_index = 0
        self.panel_index = 0
        self.border_style = border_style
        self.terminal_profile = terminal_profile or detect_terminal_profile()
        self.mouse_enabled = mouse_enabled
        self.search_results: list[SearchResult] = []
        self.last_search_query = ""

    def compose(self) -> ComposeResult:
        with Container(id="root"):
            with Horizontal(id="topbar"):
                yield Static("memtomem", id="top-title")
                yield Static("", id="mouse-status")
                yield Static("", id="top-clock")
            with Horizontal(id="layout"):
                with Vertical(id="nav", classes=self.border_class):
                    with PanelScroll(id="nav-body"):
                        yield Static("Navigation", classes="title")
                        yield Button("Dashboard", id="nav-dashboard")
                        yield Button("Search", id="nav-search")
                        yield Button("Commands", id="nav-commands")
                        yield Button("Refresh", id="nav-refresh")
                        yield Button("Help", id="nav-help")
                with Vertical(id="main", classes=self.border_class):
                    with PanelScroll(id="main-body"):
                        yield Static("Loading memtomem state...", id="main-content")
                with Vertical(id="detail", classes=self.border_class):
                    with PanelScroll(id="detail-body"):
                        yield Static("Details", classes="title")
                        yield Static(
                            "Press Ctrl+K to inspect the TUI command catalog.",
                            id="detail-text",
                        )
        yield Footer()

    async def on_mount(self) -> None:
        self.update_clock()
        self.update_mouse_status()
        self.set_interval(1, self.update_clock)
        if self.startup_refresh:
            await self.refresh_readiness()
        self.focus_panel(0)
        if has_ime_limitations(self.terminal_profile):
            self.push_screen(ConhostWarningScreen(border_style=self.border_style))

    async def on_unmount(self) -> None:
        if self._components_cm is not None:
            await self._components_cm.__aexit__(None, None, None)
            self._components_cm = None
            self.comp = None

    async def on_resize(self, event: events.Resize) -> None:
        compact = event.size.width < 100
        if compact == self.compact:
            return
        self.compact = compact
        detail = self.query_one("#detail")
        detail.display = not compact
        if compact and self.panel_index == 2:
            self.focus_panel(1)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id in self.NAV_BUTTON_IDS:
            self.focus_nav_button(self.NAV_BUTTON_IDS.index(button_id))
        else:
            self.sync_panel_from_widget(event.button)
        await self.handle_button(button_id)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-query":
            await self.run_search_from_input()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "search-results":
            self.update_search_detail(event.list_view.index)

    async def handle_button(self, button_id: str) -> None:
        if button_id == "nav-refresh":
            await self.refresh_readiness()
        elif button_id == "nav-dashboard":
            self.render_dashboard()
        elif button_id == "nav-search":
            self.render_search()
        elif button_id in {"nav-commands", "open-commands"}:
            self.render_catalog()
        elif button_id == "run-search":
            await self.run_search_from_input()
        elif button_id == "run-index":
            self.run_worker(self.index_all_memory_dirs(), exclusive=True, group="index")
        elif button_id == "refresh-after-index":
            await self.refresh_readiness()
        elif button_id == "nav-help":
            self.action_show_keybindings()
        elif button_id == "reinit-placeholder":
            self.notify(
                "Re-init flow is reserved for a later policy decision.",
                severity="warning",
            )

    async def action_refresh(self) -> None:
        await self.refresh_readiness()

    def action_show_catalog(self) -> None:
        self.render_catalog()

    def action_show_keybindings(self) -> None:
        self.push_screen(KeybindingsScreen(border_style=self.border_style))

    def action_panel_previous(self) -> None:
        self.focus_panel(self.panel_index - 1)

    def action_panel_next(self) -> None:
        self.focus_panel(self.panel_index + 1)

    def action_item_previous(self) -> None:
        self.focus_panel_item(-1)

    def action_item_next(self) -> None:
        self.focus_panel_item(1)

    def action_page_up(self) -> None:
        self.scroll_active_panel_page(-1)

    def action_page_down(self) -> None:
        self.scroll_active_panel_page(1)

    def action_toggle_mouse_mode(self) -> None:
        self.set_mouse_enabled(not self.mouse_enabled)
        mode = "TUI Mouse" if self.mouse_enabled else "OS Mouse"
        self.notify(f"Mouse mode: {mode}")

    async def action_nav_activate(self) -> None:
        focused = getattr(self, "focused", None)
        if isinstance(focused, Input) and focused.id == "search-query":
            await self.run_search_from_input()
            return
        if isinstance(focused, Button) and focused.id:
            await self.handle_button(focused.id)
            return
        await self.handle_button(self.NAV_BUTTON_IDS[self.nav_index])

    def focus_nav_button(self, index: int) -> None:
        self.nav_index = index % len(self.NAV_BUTTON_IDS)
        self.panel_index = 0
        for idx, button_id in enumerate(self.NAV_BUTTON_IDS):
            button = self.query_one(f"#{button_id}", Button)
            button.set_class(idx == self.nav_index, "active-nav")
        self.query_one(f"#{self.NAV_BUTTON_IDS[self.nav_index]}", Button).focus()
        self.set_active_panel("nav")

    def focus_panel(self, index: int) -> None:
        max_index = 1 if self.compact else len(self.PANEL_IDS) - 1
        self.panel_index = index % (max_index + 1)
        panel_id = self.PANEL_IDS[self.panel_index]
        self.set_active_panel(panel_id)

        if panel_id == "nav":
            self.focus_nav_button(self.nav_index)
            return

        focusables = self.panel_focusables(panel_id)
        if focusables:
            focusables[0].focus()
        else:
            self.panel_scroll_target(panel_id).focus()

    def focus_panel_item(self, direction: int) -> None:
        focused = getattr(self, "focused", None)
        self.sync_panel_from_widget(focused)

        panel_id = self.PANEL_IDS[self.panel_index]
        if panel_id == "nav":
            self.focus_nav_button(self.nav_index + direction)
            return

        if isinstance(focused, ListView):
            if direction < 0:
                focused.action_cursor_up()
            else:
                focused.action_cursor_down()
            return

        focusables = self.panel_focusables(panel_id)
        if not focusables:
            return

        try:
            focused_index = focusables.index(focused)
        except ValueError:
            focused_index = -1 if direction > 0 else 0
        next_index = (focused_index + direction) % len(focusables)
        focusables[next_index].focus()

    def scroll_active_panel_page(self, direction: int) -> None:
        focused = getattr(self, "focused", None)
        self.sync_panel_from_widget(focused)

        if isinstance(focused, ListView):
            self.scroll_list_view_page(focused, direction)
            return

        panel_id = self.PANEL_IDS[self.panel_index]
        scroll_target = self.panel_scroll_target(panel_id)

        if direction < 0:
            scroll_target.scroll_page_up(animate=False)
        else:
            scroll_target.scroll_page_down(animate=False)

    def scroll_list_view_page(self, list_view: ListView, direction: int) -> None:
        if not list_view.children:
            return
        current = list_view.index
        if current is None:
            current = 0 if direction > 0 else len(list_view.children) - 1
        page_size = max(1, list_view.content_size.height - 1)
        next_index = min(
            max(current + (page_size * direction), 0),
            len(list_view.children) - 1,
        )
        list_view.index = next_index
        list_view.scroll_to_widget(list_view.children[next_index], animate=False)

    def panel_focusables(self, panel_id: str) -> list[Any]:
        return list(self.query(f"#{panel_id} Input, #{panel_id} Button, #{panel_id} ListView"))

    def panel_scroll_target(self, panel_id: str) -> PanelScroll:
        body_id = {
            "nav": "nav-body",
            "main": "main-body",
            "detail": "detail-body",
        }[panel_id]
        return self.query_one(f"#{body_id}", PanelScroll)

    def set_mouse_enabled(self, enabled: bool) -> None:
        if enabled == self.mouse_enabled:
            return
        driver = getattr(self, "_driver", None)
        if driver is not None:
            if enabled:
                self._write_mouse_sequence(True)
            else:
                self._write_mouse_sequence(False)
        self.mouse_enabled = enabled
        self.update_mouse_status()

    def _write_mouse_sequence(self, enabled: bool) -> None:
        driver = getattr(self, "_driver", None)
        if driver is None:
            return
        suffix = "h" if enabled else "l"
        for mode in ("1000", "1003", "1015", "1006"):
            driver.write(f"\x1b[?{mode}{suffix}")
        driver.flush()

    def sync_panel_from_widget(self, widget: Any | None) -> None:
        if widget is None:
            return
        for index, panel_id in enumerate(self.PANEL_IDS):
            panel = self.query_one(f"#{panel_id}")
            if widget is panel or panel in getattr(widget, "ancestors", ()):
                if self.compact and panel_id == "detail":
                    return
                self.panel_index = index
                self.set_active_panel(panel_id)
                return

    def set_active_panel(self, panel_id: str) -> None:
        for candidate in self.PANEL_IDS:
            widget = self.query_one(f"#{candidate}")
            widget.set_class(candidate == panel_id, "active-panel")

    def update_clock(self) -> None:
        try:
            self.query_one("#top-clock", Static).update(datetime.now().strftime("%H:%M:%S"))
        except NoMatches:
            return

    def update_mouse_status(self) -> None:
        try:
            status = "Mouse:TUI" if self.mouse_enabled else "Mouse:OS"
            self.query_one("#mouse-status", Static).update(status)
        except NoMatches:
            return

    async def refresh_readiness(self) -> None:
        if not config_exists():
            self.readiness = Readiness(
                state=ReadinessState.SETUP_REQUIRED,
                message="memtomem is not configured yet.",
            )
            self.render_setup_required()
            return

        if self.comp is None:
            from memtomem.cli._bootstrap import cli_components

            self._components_cm = cli_components()
            self.comp = await self._components_cm.__aenter__()

        self.readiness = await inspect_readiness(self.comp)
        if self.readiness.state == ReadinessState.SETUP_REQUIRED:
            self.render_setup_required()
        elif self.readiness.state == ReadinessState.INDEX_TARGETS_REQUIRED:
            self.render_index_targets_required()
        elif self.readiness.state == ReadinessState.INDEX_REQUIRED:
            self.render_index_required()
        elif self.readiness.state == ReadinessState.ERROR:
            self.render_error()
        else:
            self.render_dashboard()

    def _main_body(self) -> PanelScroll:
        return self.query_one("#main-body", PanelScroll)

    def _detail_text(self) -> Static:
        return self.query_one("#detail-text", Static)

    async def _replace_main(self, *widgets: Static | Button | Input | ListView) -> None:
        main = self._main_body()
        main.scroll_home(animate=False)
        await main.remove_children()
        for widget in widgets:
            await main.mount(widget)

    def render_setup_required(self) -> None:
        self.run_worker(self._render_setup_required(), exclusive=True, group="render")

    async def _render_setup_required(self) -> None:
        from memtomem.cli.init_cmd import get_init_flow_definition

        flow = get_init_flow_definition()
        preset_lines = []
        for preset in flow.presets:
            marker = " (default)" if preset.default_interactive else ""
            preset_lines.append(f"- {preset.label}{marker}: {preset.description}")
        await self._replace_main(
            Static("Setup required", classes="title"),
            Static(
                "No ~/.memtomem/config.json was found. The TUI should route first-time "
                "users into a native init wizard here.",
                classes="warning",
            ),
            Static("Canonical mm init presets:", classes="title"),
            Static("\n".join(preset_lines)),
            Static(
                f"Advanced wizard: {len(flow.advanced_step_titles)} steps. "
                "Re-init policy is intentionally not implemented yet.",
                classes="muted",
            ),
            Static(
                "Implementation note: this screen is the entry point for the upcoming "
                "Textual init wizard. The existing CLI init flow remains unchanged.",
                classes="muted",
            ),
            Button("Re-run init / setup policy placeholder", id="reinit-placeholder"),
        )
        self._detail_text().update("State: SetupRequired\nNext: native init wizard.")

    def render_index_targets_required(self) -> None:
        self.run_worker(self._render_index_targets_required(), exclusive=True, group="render")

    async def _render_index_targets_required(self) -> None:
        await self._replace_main(
            Static("Memory directory required", classes="title"),
            Static("Configuration exists, but no memory directories are configured.", classes="warning"),
            Static("Add a memory directory before indexing.", classes="muted"),
            Button("Refresh", id="refresh-after-index"),
        )
        self._detail_text().update("State: IndexTargetsRequired")

    def render_index_required(self) -> None:
        self.run_worker(self._render_index_required(), exclusive=True, group="render")

    async def _render_index_required(self) -> None:
        assert self.readiness is not None
        dirs = "\n".join(f"- {p}" for p in self.readiness.memory_dirs)
        await self._replace_main(
            Static("Indexing required", classes="title"),
            Static(
                f"{self.readiness.indexable_files} indexable file(s) were found, "
                "but the index is empty.",
                classes="warning",
            ),
            Static(dirs or "(no memory dirs)", classes="muted"),
            Button("Index now", id="run-index", variant="primary"),
            Button("Refresh", id="refresh-after-index"),
            Static("", id="index-log"),
        )
        self._detail_text().update("State: IndexRequired\nAction: Index configured memory dirs.")

    def render_error(self) -> None:
        self.run_worker(self._render_error(), exclusive=True, group="render")

    async def _render_error(self) -> None:
        assert self.readiness is not None
        await self._replace_main(
            Static("Runtime error", classes="title"),
            Static(self.readiness.message, classes="error"),
            Static(self.readiness.error or "Unknown error", classes="muted"),
            Button("Refresh", id="refresh-after-index"),
        )
        self._detail_text().update("State: Error")

    def render_dashboard(self) -> None:
        self.run_worker(self._render_dashboard(), exclusive=True, group="render")

    async def _render_dashboard(self) -> None:
        if self.readiness is None:
            await self.refresh_readiness()
            return
        await self._replace_main(
            Static("Dashboard", classes="title"),
            Static(self.readiness.message, classes="ok"),
            Static(f"Chunks:  {self.readiness.total_chunks}"),
            Static(f"Sources: {self.readiness.total_sources}"),
            Static(f"Memory dirs: {len(self.readiness.memory_dirs)}", classes="muted"),
            Button("Refresh", id="refresh-after-index"),
            Button("Command catalog", id="open-commands"),
        )
        self._detail_text().update(
            "Ready for native screens:\n"
            "- Search\n"
            "- Add memory\n"
            "- Recall\n"
            "- Tags\n"
            "- Config\n"
        )

    def render_search(self) -> None:
        self.run_worker(self._render_search(), exclusive=True, group="render")

    async def _render_search(self) -> None:
        query_input = TuiInput(
            value=self.last_search_query,
            placeholder="Search memories...",
            id="search-query",
        )
        widgets: list[Static | Button | Input | ListView] = [Static("Search", classes="title")]
        if has_ime_limitations(self.terminal_profile):
            widgets.append(
                Static(
                    "Korean IME input is limited in legacy Windows consoles. "
                    "Use Windows Terminal for Korean text input.",
                    classes="warning",
                )
            )
        widgets.extend(
            [
                query_input,
                Button("Search", id="run-search", classes="tui-secondary"),
                Static("Enter a query, then press Enter or the Search button.", classes="muted"),
                ListView(id="search-results"),
            ]
        )
        await self._replace_main(
            *widgets,
        )
        self.search_results = []
        self._detail_text().update(
            "Search\n"
            "- Enter: run search from the query field\n"
            "- Up/Down: move through results\n"
            "- PgUp/PgDn: scroll results"
        )
        query_input.focus()

    async def run_search_from_input(self) -> None:
        query = self.query_one("#search-query", Input).value.strip()
        self.last_search_query = query
        if not query:
            self._detail_text().update("Search query cannot be empty.")
            return
        self.run_worker(self._run_search(query), exclusive=True, group="search")

    async def _run_search(self, query: str) -> None:
        results_view = self.query_one("#search-results", ListView)
        await results_view.clear()
        await results_view.append(ListItem(Static("Searching...")))
        self._detail_text().update(f"Searching for: {query}")

        if self.comp is None:
            await self.refresh_readiness()
        if self.comp is None:
            self._detail_text().update("Search unavailable: memtomem runtime is not initialized.")
            return

        from memtomem.server.tools.search import (
            _resolve_project_context_root as _resolve_project_context_root_from_cwd,
        )

        project_context_root = _resolve_project_context_root_from_cwd(self.comp)
        results, stats = await self.comp.search_pipeline.search(
            query,
            top_k=10,
            source_filter=None,
            tag_filter=None,
            namespace=None,
            scope=None,
            project_context_root=project_context_root,
        )
        self.search_results = list(results)
        await results_view.clear()
        if not self.search_results:
            await results_view.append(ListItem(Static("No results.")))
            self._detail_text().update(
                f"No results for: {query}\n"
                f"BM25: {stats.bm25_candidates}  Dense: {stats.dense_candidates}"
            )
            return

        for result in self.search_results:
            await results_view.append(ListItem(Static(self.search_result_label(result))))
        results_view.index = 0
        results_view.focus()
        self.update_search_detail(0, stats)

    def search_result_label(self, result: SearchResult) -> str:
        metadata = result.chunk.metadata
        source = str(metadata.source_file)
        label = " > ".join(metadata.heading_hierarchy) if metadata.heading_hierarchy else source
        snippet = " ".join(result.chunk.content.strip().split())[:64]
        return f"{result.rank:>2}. {result.score:.3f}  {label}  {snippet}"

    def update_search_detail(self, index: int | None, stats: Any | None = None) -> None:
        if index is None or index < 0 or index >= len(self.search_results):
            return
        result = self.search_results[index]
        metadata = result.chunk.metadata
        heading = " > ".join(metadata.heading_hierarchy) if metadata.heading_hierarchy else "(none)"
        tags = ", ".join(metadata.tags) if metadata.tags else "(none)"
        stats_line = ""
        if stats is not None:
            stats_line = (
                f"\n\nPipeline: {stats.bm25_candidates} BM25 + "
                f"{stats.dense_candidates} dense -> {stats.final_total} final"
            )
        self._detail_text().update(
            f"Rank: {result.rank}\n"
            f"Score: {result.score:.4f}\n"
            f"Source: {metadata.source_file}\n"
            f"Namespace: {metadata.namespace or '(default)'}\n"
            f"Heading: {heading}\n"
            f"Tags: {tags}\n\n"
            f"{result.chunk.content.strip()[:1600]}"
            f"{stats_line}"
        )

    def render_catalog(self) -> None:
        items = []
        for entry in COMMAND_CATALOG:
            label = f"{entry.command:<24} {entry.support.value:<9} {entry.title}"
            items.append(ListItem(Static(label)))
        list_view = ListView(*items)
        self.run_worker(
            self._replace_main(
                Static("TUI command catalog", classes="title"),
                Static("Tracks how existing mm commands will be surfaced in the TUI.", classes="muted"),
                list_view,
            ),
            exclusive=True,
            group="render",
        )
        self._detail_text().update("Catalog statuses: native, palette, planned, dangerous.")

    async def index_all_memory_dirs(self) -> None:
        if self.comp is None or self.readiness is None:
            await self.refresh_readiness()
            return
        log = self.query_one("#index-log", Static)
        log.update("Starting indexing...")
        total_files = 0
        indexed = 0
        skipped = 0
        deleted = 0
        errors: list[str] = []

        for root in self.readiness.memory_dirs:
            resolved = Path(root).expanduser().resolve()
            async for event in self.comp.index_engine.index_path_stream(
                resolved,
                recursive=True,
                force=False,
                namespace=None,
            ):
                event_type = event.get("type")
                if event_type == "file":
                    total_files += 1
                    current = event.get("path", str(resolved))
                    log.update(
                        f"Indexing...\n"
                        f"Files: {total_files}\n"
                        f"Indexed: {indexed}  Skipped: {skipped}  Deleted: {deleted}\n"
                        f"Current: {current}"
                    )
                elif event_type == "complete":
                    indexed += int(event.get("indexed", 0))
                    skipped += int(event.get("skipped", 0))
                    deleted += int(event.get("deleted", 0))
                elif event_type == "error":
                    errors.append(str(event.get("message", "Unknown indexing error")))

        summary = (
            "Indexing complete.\n"
            f"Files: {total_files}\n"
            f"Indexed: {indexed}  Skipped: {skipped}  Deleted: {deleted}"
        )
        if errors:
            summary += "\nErrors:\n" + "\n".join(f"- {err}" for err in errors[:8])
        log.update(summary)
        await self.refresh_readiness()


def run(
    *,
    border_style: BorderStyle = "solid",
    mouse: bool = True,
    terminal_profile: str | None = None,
) -> None:
    """Run the Textual app."""

    MemtomemTuiApp(
        border_style=border_style,
        terminal_profile=terminal_profile,
        mouse_enabled=mouse,
    ).run(mouse=mouse)


def run_input_diagnostics(
    *,
    border_style: BorderStyle = "solid",
    mouse: bool = True,
    terminal_profile: str | None = None,
) -> None:
    """Run the Textual input diagnostics app."""

    InputDiagnosticsApp(border_style=border_style, terminal_profile=terminal_profile).run(mouse=mouse)
