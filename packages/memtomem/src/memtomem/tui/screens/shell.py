"""Responsive modular shell for the independent Textual TUI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Footer, Input, Static, TextArea

from memtomem.tui.application.operations import (
    OperationRunner,
    OperationShutdownBlockedError,
)
from memtomem.tui.application.runtime import RuntimeManager
from memtomem.tui.application.tasks import TaskCenter
from memtomem.tui.mouse import driver_mouse_enabled, set_driver_mouse_enabled
from memtomem.tui.runtime import TuiPaths, config_exists, resolve_tui_paths
from memtomem.tui.shared import BorderStyleMixin, PanelScroll
from memtomem.tui.state import ROUTES, ErrorNotice, LayoutMode, ShellState
from memtomem.tui.styles import load_tui_css
from memtomem.tui.terminal import BorderStyle, detect_terminal_profile, has_ime_limitations
from memtomem.tui.widgets.modals import ConhostWarningScreen, HelpScreen, QuitConfirmScreen
from memtomem.tui.widgets.navigation import NavigationItem


class HomeSurface(VerticalScroll, can_focus=True):
    """Honest preview state while native workflows are still unavailable."""

    SETUP_READINESS = "[!] SETUP REQUIRED"
    PREVIEW_READINESS = "[ ] TUI PREVIEW"
    SETUP_GUIDANCE = (
        "No memtomem configuration was found. Run 'mm init' in the terminal; this "
        "preview does not invoke or reinterpret CLI flows."
    )
    PREVIEW_GUIDANCE = (
        "This preview does not open or migrate memory storage. Use the CLI for "
        "production workflows while native Home and Search workflows are built."
    )

    def __init__(self, *, setup_required: bool) -> None:
        super().__init__(id="home-surface", classes="home-surface")
        self.setup_required = setup_required

    def compose(self) -> ComposeResult:
        yield Static("[ HOME ]", classes="section-title", markup=False)
        yield Static(
            self.SETUP_READINESS if self.setup_required else self.PREVIEW_READINESS,
            id="home-readiness",
            classes=f"readiness-line {'warning' if self.setup_required else 'muted'}",
            markup=False,
        )
        yield Static(
            self.SETUP_GUIDANCE if self.setup_required else self.PREVIEW_GUIDANCE,
            id="home-guidance",
            classes="supporting-text",
        )
        yield Static(
            "Destinations marked with '-' are disabled preview inventory, not completed features.",
            classes="supporting-text muted",
        )

    def set_setup_required(self, setup_required: bool) -> None:
        """Refresh the cheap configuration status without rebuilding the surface."""
        self.setup_required = setup_required
        readiness = self.query_one("#home-readiness", Static)
        readiness.update(self.SETUP_READINESS if setup_required else self.PREVIEW_READINESS)
        readiness.set_class(setup_required, "warning")
        readiness.set_class(not setup_required, "muted")
        self.query_one("#home-guidance", Static).update(
            self.SETUP_GUIDANCE if setup_required else self.PREVIEW_GUIDANCE
        )


class DetailsSurface(VerticalScroll, can_focus=True):
    """Read-mostly context for the current route and selection."""

    def __init__(self) -> None:
        super().__init__(id="details-surface", classes="details-surface")

    def compose(self) -> ComposeResult:
        yield Static("[ DETAILS ]", classes="section-title", markup=False)
        yield Static("Home", classes="readiness-line")
        yield Static(
            "Context for the current route or selection appears here. Use Main for actions.",
            classes="supporting-text muted",
        )


class SafeFloor(Static, can_focus=True):
    """Minimal focus target kept usable below the supported viewport floor."""


class MemtomemTuiApp(BorderStyleMixin, App[None]):
    """Phase 2 shell: routes, responsive regions, global state, errors, and details."""

    CSS = load_tui_css()
    BINDINGS = [
        Binding("escape", "escape", "Escape", show=False),
        Binding("ctrl+q", "request_quit", "Quit", priority=True),
        Binding("ctrl+r", "refresh", "Refresh", priority=True),
        Binding("?", "show_keybindings", "Help", priority=True),
        Binding("up,k", "item_previous", "Previous item", show=False),
        Binding("down,j", "item_next", "Next item", show=False),
        Binding("left,h", "item_left", "Previous item", show=False),
        Binding("right,l", "item_right", "Next item", show=False),
        Binding(
            "left_square_bracket",
            "focus_previous_section",
            "Previous panel",
            show=False,
        ),
        Binding(
            "right_square_bracket",
            "focus_next_section",
            "Next panel",
            show=False,
        ),
        Binding("page_up", "page_up", "Page up", show=False),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("page_down", "page_down", "Page down", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
        Binding("f2", "focus_menu", "Navigation", show=False, priority=True),
        Binding("f3", "focus_main", "Main", show=False, priority=True),
        Binding("f4", "focus_detail", "Details", show=False, priority=True),
        Binding("f6,alt+m", "toggle_mouse_mode", "Mouse mode", show=False, priority=True),
        Binding("f7", "tab_previous", "Previous tab", show=False, priority=True),
        Binding("f8", "tab_next", "Next tab", show=False, priority=True),
        Binding("enter", "nav_activate", "Open", show=False),
    ]
    SECTION_IDS = ("nav", "main", "detail")

    def __init__(
        self,
        *,
        border_style: BorderStyle = "solid",
        startup_refresh: bool = True,
        terminal_profile: str | None = None,
        mouse_enabled: bool = True,
        paths: TuiPaths | None = None,
        task_center: TaskCenter | None = None,
        operation_runner: OperationRunner | None = None,
        runtime_manager: RuntimeManager[Any] | None = None,
    ) -> None:
        super().__init__()
        self.border_style = border_style
        self.startup_refresh = startup_refresh
        self.terminal_profile = terminal_profile or detect_terminal_profile()
        self.paths = paths or resolve_tui_paths(dev=False)
        self._initial_mouse_enabled = mouse_enabled
        self.state = ShellState()
        self.task_center = task_center or TaskCenter()
        self.operation_runner = operation_runner or OperationRunner()
        self.runtime_manager = runtime_manager or RuntimeManager(self.paths)
        self._services_shutdown = False

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            with Horizontal(id="topbar"):
                yield Static(
                    "memtomem / TUI preview",
                    id="app-title",
                    classes="app-title",
                )
                if self.paths.is_dev:
                    yield Static(
                        "DEV",
                        id="environment-status",
                        classes="status-item environment-status warning secondary-status",
                    )
                yield Static(
                    "MOUSE:ON",
                    id="mouse-status",
                    classes="status-item mouse-status secondary-status",
                )
                yield Static("", id="clock-status", classes="status-item clock-status")
            with PanelScroll(
                id="navigation",
                classes=f"nav-section {self.border_class}".strip(),
            ):
                yield Static(
                    "[ NAVIGATION ]",
                    id="navigation-title",
                    classes="section-title",
                    markup=False,
                )
                yield from (NavigationItem(route) for route in ROUTES)
                yield Static(
                    "- planned",
                    id="navigation-legend",
                    classes="supporting-text muted",
                )
            yield Static("", id="global-error", classes="error-banner", markup=False)
            with Horizontal(id="shell-content"):
                with Vertical(
                    id="main", classes=f"section-panel main-section {self.border_class}".strip()
                ):
                    yield HomeSurface(
                        setup_required=self.startup_refresh
                        and not config_exists(self.paths.config_path)
                    )
                with Vertical(
                    id="detail",
                    classes=f"section-panel detail-section {self.border_class}".strip(),
                ):
                    yield DetailsSurface()
            yield SafeFloor(
                "Resize to at least 32 columns x 8 rows.  ? Help   Ctrl+Q Quit",
                id="safe-floor",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#global-error").display = False
        driver = self._driver
        if driver is not None and self.mouse_enabled != self._initial_mouse_enabled:
            try:
                set_driver_mouse_enabled(driver, self._initial_mouse_enabled)
            except (AttributeError, OSError, RuntimeError) as exc:
                self._report_mouse_mode_error(exc)
        self._apply_layout(LayoutMode.from_viewport(self.size.width, self.size.height))
        self._update_route_classes()
        self._update_clock()
        self._update_mouse_status()
        self.set_interval(1, self._update_clock)
        self.activate_section("nav")
        if has_ime_limitations(self.terminal_profile):
            self.push_screen(
                ConhostWarningScreen(border_style=self.border_style),
                callback=lambda _: self._restore_layout_focus(),
            )

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(LayoutMode.from_viewport(event.size.width, event.size.height))

    def _apply_layout(self, mode: LayoutMode) -> None:
        previous = self.state.layout_mode
        self.state.layout_mode = mode
        for candidate in LayoutMode:
            self.set_class(candidate is mode, f"layout-{candidate.value}")
        compact_labels = mode is not LayoutMode.WIDE
        for item in self.query(NavigationItem):
            item.set_compact(compact_labels)
        self.query_one("#app-title", Static).update(
            "memtomem"
            if mode in {LayoutMode.EXTREME, LayoutMode.SAFE_FLOOR}
            else "memtomem / TUI preview"
        )
        self._update_section_classes()
        if self.screen.is_modal:
            return
        if mode is LayoutMode.SAFE_FLOOR or previous is LayoutMode.SAFE_FLOOR:
            self._restore_layout_focus()

    def _restore_layout_focus(self) -> None:
        if self.screen.is_modal:
            return
        if self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            self.query_one("#safe-floor", SafeFloor).focus()
            return
        self.activate_section(self.state.active_section)

    def _update_section_classes(self) -> None:
        for section in self.SECTION_IDS:
            self.set_class(section == self.state.active_section, f"section-{section}")
            try:
                panel = self.query_one(self._section_selector(section))
            except NoMatches:
                continue
            panel.set_class(section == self.state.active_section, "active-section")

    def activate_section(self, section: str) -> None:
        self._remember_current_focus()
        self.state.activate(section)
        self._update_section_classes()
        if self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            self.query_one("#safe-floor", SafeFloor).focus()
            return
        target_id = self.state.remembered_focus.get(section)
        target = self._focusable_by_id(target_id) or self._section_focusables(section)[0]
        target.focus()

    def _remember_current_focus(self) -> None:
        focused = self.focused
        section = self.section_for_widget(focused)
        if section and focused is not None and focused.id:
            self.state.remembered_focus[section] = focused.id

    def _focusable_by_id(self, widget_id: str | None) -> Any | None:
        if not widget_id:
            return None
        try:
            widget = self.query_one(f"#{widget_id}")
        except NoMatches:
            return None
        return widget if widget.can_focus and not widget.disabled and widget.display else None

    def _section_focusables(self, section: str) -> list[Any]:
        panel = self.query_one(self._section_selector(section))
        candidates = [widget for widget in panel.query("*") if widget.can_focus]
        return [widget for widget in candidates if not widget.disabled and widget.display] or [
            panel
        ]

    @staticmethod
    def _section_selector(section: str) -> str:
        return {"nav": "#navigation", "main": "#main", "detail": "#detail"}[section]

    def section_for_widget(self, widget: Any | None) -> str | None:
        current = widget
        while current is not None:
            if current.id == "navigation":
                return "nav"
            if current.id in {"main", "home-surface"}:
                return "main"
            if current.id in {"detail", "details-surface"}:
                return "detail"
            current = getattr(current, "parent", None)
        return None

    def synchronize_pointer_target(self, widget: Any) -> None:
        section = self.section_for_widget(widget)
        if section:
            self._remember_current_focus()
            self.state.activate(section)
            self._update_section_classes()
            current = widget
            while current is not None and self.section_for_widget(current) == section:
                if current.can_focus and not current.disabled and current.display:
                    current.focus()
                    return
                current = getattr(current, "parent", None)
            self._section_focusables(section)[0].focus()

    def is_widget_actionable(self, widget: Any) -> bool:
        """Return whether keyboard activation may run for a section widget."""
        section = self.section_for_widget(widget)
        if section is None:
            return True
        return (
            self.state.layout_mode is not LayoutMode.SAFE_FLOOR
            and section == self.state.active_section
        )

    def on_click(self, event: events.Click) -> None:
        """Synchronize section state for clicks on non-actionable panel content."""
        widget, _ = self.screen.get_widget_at(event.screen_x, event.screen_y)
        self.synchronize_pointer_target(widget)

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        section = self.section_for_widget(event.widget)
        if section == self.state.active_section and event.widget.id:
            self.state.remembered_focus[section] = event.widget.id

    def on_navigation_item_selected(self, event: NavigationItem.Selected) -> None:
        self.state.route_id = event.route_id
        self._update_route_classes()

    def _update_route_classes(self) -> None:
        for item in self.query(NavigationItem):
            item.set_class(item.route.id == self.state.route_id, "route-active")

    async def action_refresh(self) -> None:
        if self.screen.is_modal:
            return
        setup_required = self.startup_refresh and not config_exists(self.paths.config_path)
        self.query_one(HomeSurface).set_setup_required(setup_required)

    def action_show_keybindings(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.screen.dismiss(None)
            return
        if self.screen.is_modal:
            return
        self.push_screen(
            HelpScreen(border_style=self.border_style),
            callback=lambda _: self._restore_layout_focus(),
        )

    def action_request_quit(self) -> None:
        if self.screen.is_modal:
            return
        # Textual's App[None] worker overload expects Never even though a modal
        # callback returns normally. Passing the callable is intentionally lazy.
        self.run_worker(
            self._confirm_quit,  # type: ignore[arg-type]
            group="quit",
            exclusive=True,
        )

    async def _confirm_quit(self) -> None:
        if await self.push_screen_wait(QuitConfirmScreen(border_style=self.border_style)):
            if await self._shutdown_services():
                self.exit()
                return
            self._restore_layout_focus()
            return
        self._restore_layout_focus()

    async def on_unmount(self) -> None:
        """Close lazy runtime/application work when the app is stopped externally."""

        if self._services_shutdown:
            return
        await self.operation_runner.force_shutdown()
        await self.runtime_manager.close()
        self._services_shutdown = True

    async def _shutdown_services(self, *, report_blocker: bool = True) -> bool:
        """Apply operation exit policy, then close every runtime generation."""

        if self._services_shutdown:
            return True
        try:
            await self.operation_runner.shutdown()
        except OperationShutdownBlockedError:
            if report_blocker:
                self.report_error(
                    ErrorNotice(
                        code="TUI-EXIT-BLOCKED",
                        message="A critical operation must finish before exit.",
                        detail=None,
                        recoverable=True,
                    )
                )
            return False
        await self.runtime_manager.close()
        self._services_shutdown = True
        if self.runtime_manager.close_errors:
            if report_blocker:
                self.report_error(
                    ErrorNotice(
                        code="TUI-RUNTIME-CLOSE",
                        message="Some runtime resources could not be closed cleanly.",
                        detail=None,
                        recoverable=False,
                    )
                )
            return False
        return True

    def action_escape(self) -> None:
        if self.screen.is_modal:
            return
        if self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            self.action_request_quit()
            return
        focused = self.focused
        if isinstance(focused, (Input, TextArea)):
            section = self.section_for_widget(focused)
            current = getattr(focused, "parent", None)
            while section is not None and current is not None:
                if self.section_for_widget(current) != section:
                    break
                if current.can_focus and not current.disabled and current.display:
                    current.focus()
                    return
                current = getattr(current, "parent", None)
        previous = {"detail": "main", "main": "nav"}.get(self.state.active_section)
        if previous is None:
            self.action_request_quit()
            return
        self.activate_section(previous)

    def action_focus_menu(self) -> None:
        self._activate_section_from_key("nav")

    def action_focus_main(self) -> None:
        self._activate_section_from_key("main")

    def action_focus_detail(self) -> None:
        self._activate_section_from_key("detail")

    def _activate_section_from_key(self, section: str) -> None:
        if self.screen.is_modal or self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            return
        self.activate_section(section)

    def action_focus_previous_section(self) -> None:
        self._move_section(-1)

    def action_focus_next_section(self) -> None:
        self._move_section(1)

    def _move_section(self, direction: int) -> None:
        if self.screen.is_modal or self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            return
        current = self.SECTION_IDS.index(self.state.active_section)
        target = current + direction
        if 0 <= target < len(self.SECTION_IDS):
            self.activate_section(self.SECTION_IDS[target])

    def action_item_previous(self) -> None:
        if self.screen.is_modal or self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            return
        self._move_focus(-1)

    def action_item_next(self) -> None:
        if self.screen.is_modal or self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            return
        self._move_focus(1)

    def _move_focus(self, direction: int) -> None:
        focusables = self._section_focusables(self.state.active_section)
        try:
            index = focusables.index(self.focused)
        except ValueError:
            index = 0
        target = focusables[max(0, min(len(focusables) - 1, index + direction))]
        target.focus()
        target.scroll_visible(animate=False)

    def action_item_left(self) -> None:
        if self.screen.is_modal or self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            return
        self._move_focus(-1)

    def action_item_right(self) -> None:
        if self.screen.is_modal or self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            return
        self._move_focus(1)

    def action_page_up(self) -> None:
        self._scroll_active(-1)

    def action_page_down(self) -> None:
        self._scroll_active(1)

    def _scroll_active(self, direction: int) -> None:
        if self.screen.is_modal or self.state.layout_mode is LayoutMode.SAFE_FLOOR:
            return
        panel = self.query_one(self._section_selector(self.state.active_section))
        target = next(iter(panel.query(VerticalScroll)), panel)
        if direction < 0:
            target.scroll_page_up(animate=False)
        else:
            target.scroll_page_down(animate=False)

    def action_tab_previous(self) -> None:
        return

    def action_tab_next(self) -> None:
        return

    def action_nav_activate(self) -> None:
        focused = self.focused
        if self.state.active_section == "nav" and isinstance(focused, NavigationItem):
            if not focused.disabled:
                focused.post_message(NavigationItem.Selected(focused.route.id))

    def action_toggle_mouse_mode(self) -> None:
        driver = self._driver
        if driver is None:
            return
        try:
            set_driver_mouse_enabled(driver, not self.mouse_enabled)
        except (AttributeError, OSError, RuntimeError) as exc:
            self._report_mouse_mode_error(exc)
        self._update_mouse_status()

    def _report_mouse_mode_error(self, error: Exception) -> None:
        self.report_error(
            ErrorNotice(
                code="TUI-MOUSE-MODE",
                message="Mouse mode could not be changed.",
                detail=str(error),
                recoverable=True,
            )
        )

    @property
    def mouse_enabled(self) -> bool:
        """Return the active Textual driver's mouse state."""

        return driver_mouse_enabled(self._driver, default=self._initial_mouse_enabled)

    def _update_mouse_status(self) -> None:
        try:
            self.query_one("#mouse-status", Static).update(
                "MOUSE:ON" if self.mouse_enabled else "MOUSE:OS"
            )
        except NoMatches:
            pass

    def _update_clock(self) -> None:
        try:
            self.query_one("#clock-status", Static).update(datetime.now().strftime("%H:%M:%S"))
        except NoMatches:
            pass

    def report_error(self, notice: ErrorNotice) -> None:
        self.state.error = notice
        banner = self.query_one("#global-error", Static)
        banner.update(self._error_text(notice))
        banner.display = True
        self.notify(
            f"{notice.code}: {notice.message}",
            severity="error",
            timeout=8,
            markup=False,
        )

    @staticmethod
    def _error_text(notice: ErrorNotice) -> str:
        recovery = " | recovery available" if notice.recoverable else ""
        return f"[x] {notice.code}: {notice.message}{recovery}"
