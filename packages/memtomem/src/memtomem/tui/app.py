"""Textual application entry point for ``mm tui``."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from pathlib import Path
from typing import Any

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, ListItem, ListView, Static

from memtomem.tui.catalog import COMMAND_CATALOG
from memtomem.tui.runtime import Readiness, ReadinessState, config_exists, inspect_readiness
from memtomem.tui.shared import COMMON_PANEL_CSS, BorderStyleMixin, PanelScroll
from memtomem.tui.terminal import BorderStyle


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
                "  r               Refresh",
                "  ?               Show this keymap",
                "  q               Quit",
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
        Binding("enter", "nav_activate", "Open menu", show=False),
    ]

    NAV_BUTTON_IDS = ("nav-dashboard", "nav-commands", "nav-refresh", "nav-help")
    PANEL_IDS = ("nav", "main", "detail")

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self._components_cm: AbstractAsyncContextManager[Any] | None = None
        self.comp: Any | None = None
        self.readiness: Readiness | None = None
        self.compact = False
        self.nav_index = 0
        self.panel_index = 0
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        with Container(id="root"):
            with Horizontal(id="topbar"):
                yield Static("memtomem", id="top-title")
                yield Static("", id="top-clock")
            with Horizontal(id="layout"):
                with Vertical(id="nav", classes=self.border_class):
                    with PanelScroll(id="nav-body"):
                        yield Static("Navigation", classes="title")
                        yield Button("Dashboard", id="nav-dashboard")
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
        self.set_interval(1, self.update_clock)
        await self.refresh_readiness()
        self.focus_panel(0)

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

    async def handle_button(self, button_id: str) -> None:
        if button_id == "nav-refresh":
            await self.refresh_readiness()
        elif button_id == "nav-dashboard":
            self.render_dashboard()
        elif button_id in {"nav-commands", "open-commands"}:
            self.render_catalog()
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

    async def action_nav_activate(self) -> None:
        focused = getattr(self, "focused", None)
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
        return list(self.query(f"#{panel_id} Button, #{panel_id} ListView"))

    def panel_scroll_target(self, panel_id: str) -> PanelScroll:
        body_id = {
            "nav": "nav-body",
            "main": "main-body",
            "detail": "detail-body",
        }[panel_id]
        return self.query_one(f"#{body_id}", PanelScroll)

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
        self.query_one("#top-clock", Static).update(datetime.now().strftime("%H:%M:%S"))

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

    async def _replace_main(self, *widgets: Static | Button | ListView) -> None:
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


def run(*, border_style: BorderStyle = "solid") -> None:
    """Run the Textual app."""

    MemtomemTuiApp(border_style=border_style).run()
