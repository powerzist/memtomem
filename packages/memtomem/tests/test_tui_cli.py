"""Phase 2 contract tests for the independent modular Textual shell."""

from __future__ import annotations

from html import unescape
import inspect
from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Static

from memtomem.tui.app import (
    ConhostWarningScreen,
    MemtomemTuiApp,
    QuitConfirmScreen,
    run,
    run_input_diagnostics,
)
from memtomem.tui.application.tasks import (
    TaskCancellationPolicy,
    TaskCenter,
    TaskExitPolicy,
    TaskStatus,
    TaskSurfaceEffect,
)
from memtomem.tui.clipboard import ClipboardAppMixin
from memtomem.tui.runtime import TuiPaths
from memtomem.tui.state import ROUTES, ErrorNotice, LayoutMode
from memtomem.tui.widgets.controls import ModalButton, PanelButton, TuiInput
from memtomem.tui.widgets.modals import HelpScreen
from memtomem.tui.widgets.navigation import NavigationItem


class _InputTestApp(ClipboardAppMixin, App[None]):
    def compose(self) -> ComposeResult:
        yield TuiInput(value="abcdef", id="test-input")


def _paths(tmp_path: Path, *, configured: bool = True) -> TuiPaths:
    root = tmp_path / ".memtomem"
    root.mkdir()
    if configured:
        (root / "config.json").write_text("{}\n", encoding="utf-8")
    return TuiPaths(
        mode="dev",
        project_root=tmp_path,
        state_root=root,
        config_path=root / "config.json",
        config_d_path=root / "config.d",
        database_path=root / "memtomem.db",
        memories_path=root / "memories",
    )


def _app(tmp_path: Path, **kwargs: object) -> MemtomemTuiApp:
    return MemtomemTuiApp(
        startup_refresh=True,
        terminal_profile="windows-terminal",
        paths=_paths(tmp_path),
        **kwargs,
    )


def _rendered_text(root: object) -> str:
    return "\n".join(str(widget.render()) for widget in root.query(Static))


def _rendered_button_text(button: ModalButton) -> str:
    return "\n".join(button.render_line(row).text for row in range(button.region.height))


def _composed_screen_line(app: MemtomemTuiApp, row: int) -> str:
    """Return the fully composited row used by screenshots and terminal output."""
    return app.screen._compositor.render_strips()[row].text


def test_launcher_signatures_remain_stable() -> None:
    assert tuple(inspect.signature(run).parameters) == (
        "border_style",
        "mouse",
        "terminal_profile",
        "paths",
    )
    assert tuple(inspect.signature(run_input_diagnostics).parameters) == (
        "border_style",
        "mouse",
        "terminal_profile",
    )


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (160, 50, LayoutMode.WIDE),
        (120, 30, LayoutMode.WIDE),
        (100, 24, LayoutMode.WIDE),
        (99, 24, LayoutMode.STANDARD),
        (80, 24, LayoutMode.STANDARD),
        (60, 16, LayoutMode.STANDARD),
        (59, 16, LayoutMode.COMPACT),
        (60, 15, LayoutMode.COMPACT),
        (60, 11, LayoutMode.COMPACT),
        (48, 12, LayoutMode.COMPACT),
        (41, 11, LayoutMode.COMPACT),
        (160, 10, LayoutMode.EXTREME),
        (40, 11, LayoutMode.EXTREME),
        (40, 10, LayoutMode.EXTREME),
        (32, 8, LayoutMode.EXTREME),
        (31, 8, LayoutMode.SAFE_FLOOR),
        (40, 7, LayoutMode.SAFE_FLOOR),
    ],
)
def test_layout_mode_uses_authoritative_breakpoints(
    width: int, height: int, expected: LayoutMode
) -> None:
    assert LayoutMode.from_viewport(width, height) is expected


async def test_shell_removes_old_test_catalog_and_color_preview(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)):
        labels = [item.route.label for item in app.query(NavigationItem)]
        assert labels == [route.label for route in ROUTES]
        assert "Test" not in labels
        assert "Commands" not in labels
        assert "color preview" not in _rendered_text(app.screen)


async def test_unimplemented_routes_are_honest_disabled_inventory(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)):
        items = list(app.query(NavigationItem))
        assert items[0].route.id == "home"
        assert items[0].disabled is False
        assert items[0].has_class("route-active")
        assert items[1].route.id == "memories"
        assert items[1].disabled is False
        assert all(item.disabled for item in items[2:])


@pytest.mark.parametrize(
    ("size", "expected_mode"),
    [
        ((120, 30), LayoutMode.WIDE),
        ((80, 24), LayoutMode.STANDARD),
        ((60, 16), LayoutMode.STANDARD),
    ],
)
async def test_split_shell_exposes_navigation_main_and_details_at_terminal_defaults(
    tmp_path: Path,
    size: tuple[int, int],
    expected_mode: LayoutMode,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=size):
        navigation = app.query_one("#navigation")
        main = app.query_one("#main")
        detail = app.query_one("#detail")
        shell = app.query_one("#shell-content")

        assert app.state.layout_mode is expected_mode
        assert navigation.display and navigation.region.height == 1
        navigation_line = _composed_screen_line(app, navigation.region.y)
        expected_memory_label = "Memories" if expected_mode is LayoutMode.WIDE else "Memory"
        assert "Home" in navigation_line
        assert expected_memory_label in navigation_line
        assert len(navigation_line) == size[0]
        assert navigation.scrollbar_size_horizontal == 0
        assert main.display and main.region.width > 0
        assert detail.display and detail.region.width > 0
        assert main.region.width + detail.region.width == size[0]
        assert shell.virtual_size.width <= shell.region.width
        root = app.query_one("#root")
        assert root.virtual_size.width <= root.region.width
        assert "HOME DETAILS" in _rendered_text(detail)
        assert not app.query("#task-status")
        assert app.query_one("#environment-status").region.width == 4
        assert app.query_one("#mouse-status").region.width == 12
        assert app.query_one("#clock-status").region.width == 10

        clock = str(app.query_one("#clock-status", Static).render())
        assert len(clock) == 8
        assert all(len(part) == 2 and part.isdigit() for part in clock.split(":"))


@pytest.mark.parametrize(
    ("size", "expected_route_label"),
    [
        ((120, 30), "Memories"),
        ((80, 24), "Memory"),
        ((60, 16), "Memory"),
    ],
)
async def test_split_navigation_text_occupies_its_single_rendered_row(
    tmp_path: Path,
    size: tuple[int, int],
    expected_route_label: str,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=size):
        navigation = app.query_one("#navigation")
        screenshot = unescape(app.export_screenshot()).replace("\N{NO-BREAK SPACE}", " ")

        assert navigation.region.height == 1
        assert navigation.styles.scrollbar_size_horizontal == 0
        assert f"  {expected_route_label}" in screenshot


async def test_split_navigation_scrolls_the_focused_route_into_its_single_row(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(60, 16)) as pilot:
        navigation = app.query_one("#navigation")
        services = app.query_one("#route-services", NavigationItem)
        services.disabled = False

        await pilot.press("right", "right")
        await pilot.pause()

        assert app.focused is services
        assert navigation.scroll_x > 0
        assert navigation.region.height == 1
        assert navigation.virtual_size.height == 1
        assert "Services" in _composed_screen_line(app, navigation.region.y)
        assert app.query_one("#shell-content").virtual_size.width <= 60


async def test_section_hotkeys_update_active_section_and_focus(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.press("f3")
        assert app.state.active_section == "main"
        assert app.section_for_widget(app.focused) == "main"
        await pilot.press("f4")
        assert app.state.active_section == "detail"
        assert app.section_for_widget(app.focused) == "detail"
        await pilot.press("f2")
        assert app.state.active_section == "nav"
        assert app.section_for_widget(app.focused) == "nav"


async def test_mouse_toggle_remains_global_from_input_focus(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        surface = app.query_one("#home-surface")
        field = TuiInput(id="mouse-test-input")
        await surface.mount(field)
        app.activate_section("main")
        field.focus()

        await pilot.press("f6")
        assert app.mouse_enabled is False
        assert str(app.query_one("#mouse-status", Static).render()) == "MOUSE:OS"
        await pilot.press("alt+m")
        assert app.mouse_enabled is True


async def test_initial_no_mouse_mode_is_synced_to_the_active_driver(tmp_path: Path) -> None:
    app = _app(tmp_path, mouse_enabled=False)
    async with app.run_test(size=(100, 24)) as pilot:
        assert app.mouse_enabled is False
        assert str(app.query_one("#mouse-status", Static).render()) == "MOUSE:OS"

        await pilot.press("f6")
        assert app.mouse_enabled is True
        assert str(app.query_one("#mouse-status", Static).render()) == "MOUSE:TUI"


async def test_mouse_toggle_failure_is_reported_without_false_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        driver = app._driver
        assert driver is not None

        def fail_disable() -> None:
            raise OSError("private terminal failure")

        monkeypatch.setattr(driver, "_disable_mouse_support", fail_disable, raising=False)
        await pilot.press("f6")

        assert app.mouse_enabled is True
        assert str(app.query_one("#mouse-status", Static).render()) == "MOUSE:TUI"
        assert app.state.error is not None
        assert app.state.error.code == "TUI-MOUSE-MODE"
        assert "private terminal failure" not in _rendered_text(app.screen)


async def test_tab_hotkeys_are_noops_when_active_section_has_no_tabs(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        focused = app.focused
        await pilot.press("f7", "f8")
        assert app.state.active_section == "nav"
        assert app.focused is focused


async def test_split_layout_keeps_main_and_details_visible_while_focus_changes(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        assert app.state.layout_mode is LayoutMode.STANDARD
        assert "Agents  -" in str(app.query_one("#route-collaboration").render())
        await pilot.press("f4")
        assert app.state.active_section == "detail"
        assert app.query_one("#navigation").display
        assert app.query_one("#main").display
        assert app.query_one("#detail").display


@pytest.mark.parametrize("size", [(59, 16), (60, 15)])
async def test_compact_layout_shows_only_active_section(
    tmp_path: Path,
    size: tuple[int, int],
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=size) as pilot:
        assert app.query_one("#navigation").display
        assert not app.query_one("#main").display
        assert not app.query_one("#detail").display
        await pilot.press("f3")
        assert not app.query_one("#navigation").display
        assert app.query_one("#main").display
        assert not app.query_one("#detail").display
        await pilot.press("f4")
        assert not app.query_one("#navigation").display
        assert not app.query_one("#main").display
        assert app.query_one("#detail").display


async def test_extreme_layout_uses_short_labels_and_scrollable_navigation(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(32, 8)) as pilot:
        navigation = app.query_one("#navigation")
        collaboration = app.query_one("#route-collaboration", NavigationItem)
        assert app.state.layout_mode is LayoutMode.EXTREME
        assert "Agents  -" in str(collaboration.render())
        assert "Agents & Sessions" not in str(collaboration.render())
        assert navigation.styles.overflow_y == "auto"
        assert navigation.virtual_size.height > navigation.container_size.height
        assert app.query_one("#topbar").virtual_size.height == 1

        await pilot.press("page_down")
        assert navigation.scroll_y > 0
        await pilot.press("f3")
        assert not app.query_one("#navigation").display
        assert app.query_one("#main").display
        assert not app.query_one("#detail").display


async def test_safe_floor_keeps_help_and_quit_instructions_visible(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(31, 8)):
        assert app.state.layout_mode is LayoutMode.SAFE_FLOOR
        floor = app.query_one("#safe-floor", Static)
        topbar = app.query_one("#topbar")
        assert floor.display
        assert app.focused is floor
        assert topbar.virtual_size.width <= topbar.region.width
        assert "? Help" in str(floor.render())
        assert "Ctrl+Q Quit" in str(floor.render())


async def test_safe_floor_resize_restores_visible_active_section_focus(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("f3")
        assert app.state.active_section == "main"

        await pilot.resize_terminal(31, 8)
        assert app.state.layout_mode is LayoutMode.SAFE_FLOOR
        assert getattr(app.focused, "id", None) == "safe-floor"

        await pilot.resize_terminal(100, 24)
        assert app.state.active_section == "main"
        assert app.section_for_widget(app.focused) == "main"


async def test_resize_preserves_route_active_section_and_headless_tasks(tmp_path: Path) -> None:
    tasks = TaskCenter()
    record = tasks.create("Index files", cancellable=True)
    tasks.update(record.id, status=TaskStatus.RUNNING, phase="Embedding", progress=0.5)
    app = _app(tmp_path, task_center=tasks)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.press("f4")
        app.state.route_id = "home"
        await pilot.resize_terminal(60, 16)
        assert app.state.route_id == "home"
        assert app.state.active_section == "detail"
        assert app.task_center.get(record.id).progress == 0.5
        assert not app.query(".task-row")
        assert "DETAILS" in _rendered_text(app.query_one("#detail"))


def test_task_center_records_structured_terminal_states() -> None:
    tasks = TaskCenter()
    record = tasks.create("Reindex", parameters={"root": "C:/memories"}, cancellable=True)
    running = tasks.update(
        record.id,
        status=TaskStatus.RUNNING,
        phase="Chunking",
        progress=0.25,
        completed=5,
        remaining=15,
    )
    failed = tasks.update(
        record.id,
        status=TaskStatus.PARTIAL,
        phase="Completed with errors",
        failed=2,
        warnings=("Two files were skipped",),
        recovery_action="Retry failed files",
    )
    assert running.started_at is not None
    assert failed.ended_at is not None
    assert failed.status is TaskStatus.PARTIAL
    assert failed.recovery_action == "Retry failed files"
    assert failed.navigation_effect is TaskSurfaceEffect.NONE
    assert failed.resize_effect is TaskSurfaceEffect.NONE
    assert failed.exit_policy is TaskExitPolicy.PROMPT
    assert failed.cancellation_policy is TaskCancellationPolicy.COOPERATIVE_KEEP_COMPLETED


async def test_task_registry_remains_headless_while_details_stay_contextual(
    tmp_path: Path,
) -> None:
    tasks = TaskCenter()
    app = _app(tmp_path, task_center=tasks)
    async with app.run_test(size=(100, 24)) as pilot:
        task = tasks.create("Index files", cancellable=True)
        tasks.update(task.id, status=TaskStatus.RUNNING, phase="Embedding", progress=0.5)
        await pilot.pause()

        assert app.task_center.get(task.id).phase == "Embedding"
        assert not app.query(".task-row")
        assert not app.query("#task-status")
        assert "HOME DETAILS" in _rendered_text(app.query_one("#home-details-surface"))


async def test_help_is_keyboard_reachable_and_escape_closes(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("?")
        assert isinstance(app.screen, HelpScreen)
        help_text = _rendered_text(app.screen)
        assert "F2  Navigation" in help_text
        assert "Arrows or h/j/k/l Move within active panel" in help_text
        assert "[ / ]" in help_text
        assert "Previous/next panel (no wrap)" in help_text
        assert "Detail -> Main -> Navigation -> Quit confirmation" in help_text
        dialog = app.screen.query_one(".modal-dialog")
        assert dialog.region.x > 0
        assert dialog.region.y > 0
        await pilot.press("escape")
        assert not isinstance(app.screen, HelpScreen)


async def test_help_key_toggles_without_stacking_and_restores_focus(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("f3")
        invoking_focus = app.focused

        await pilot.press("?")
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("?")
        await pilot.pause()

        assert not isinstance(app.screen, HelpScreen)
        assert app.focused is invoking_focus


async def test_help_key_does_not_replace_another_modal(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("ctrl+q")
        quit_screen = app.screen

        await pilot.press("?")

        assert app.screen is quit_screen
        assert isinstance(app.screen, QuitConfirmScreen)
        await pilot.press("escape")


async def test_modal_button_labels_render_as_literal_text(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("?")
        close = app.screen.query_one("#help-close", ModalButton)
        assert str(close.label) == "[ CLOSE ]"
        assert "[ CLOSE ]" in _rendered_button_text(close)
        await pilot.press("escape")

        await pilot.press("ctrl+q")
        yes = app.screen.query_one("#quit-yes", ModalButton)
        no = app.screen.query_one("#quit-no", ModalButton)
        assert str(yes.label) == "[ YES ]"
        assert str(no.label) == "[ NO ]"
        assert "[ YES ]" in _rendered_button_text(yes)
        assert "[ NO ]" in _rendered_button_text(no)
        await pilot.press("escape")

        app.push_screen(ConhostWarningScreen())
        await pilot.pause()
        warning = app.screen.query_one("#warning-close", ModalButton)
        assert str(warning.label) == "[ CONTINUE ]"
        assert "[ CONTINUE ]" in _rendered_button_text(warning)
        await pilot.press("escape")


async def test_help_scrolls_and_restores_invoking_focus(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(40, 10)) as pilot:
        await pilot.press("f3")
        invoking_focus = app.focused
        await pilot.press("?")
        body = app.screen.query_one(".modal-body")
        assert body.scroll_y == 0
        await pilot.press("pagedown")
        await pilot.pause()
        assert body.scroll_y > 0
        await pilot.press("escape")
        await pilot.pause()
        assert app.focused is invoking_focus


async def test_quit_confirmation_defaults_to_no_and_escape_cancels(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("ctrl+q")
        assert isinstance(app.screen, QuitConfirmScreen)
        assert app.screen.focused is not None
        assert app.screen.focused.id == "quit-no"
        dialog = app.screen.query_one(".modal-dialog")
        assert app.screen.region.contains_region(dialog.region)
        assert all(
            dialog.region.contains_region(button.region) for button in app.screen.query(Button)
        )
        await pilot.press("up")
        assert app.screen.focused.id == "quit-yes"
        await pilot.press("down")
        assert app.screen.focused.id == "quit-no"
        await pilot.press("escape")
        assert not isinstance(app.screen, QuitConfirmScreen)


async def test_extreme_quit_confirmation_keeps_buttons_inside_dialog(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(32, 8)) as pilot:
        await pilot.press("ctrl+q")
        dialog = app.screen.query_one(".modal-dialog")
        assert app.screen.region.contains_region(dialog.region)
        assert all(
            dialog.region.contains_region(button.region) for button in app.screen.query(Button)
        )
        await pilot.press("escape")


async def test_quit_no_enter_restores_invoking_focus(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("f3")
        invoking_focus = app.focused
        await pilot.press("ctrl+q")
        assert getattr(app.screen.focused, "id", None) == "quit-no"
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, QuitConfirmScreen)
        assert app.focused is invoking_focus


async def test_conhost_startup_warning_remains_keyboard_dismissible(tmp_path: Path) -> None:
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-conhost",
        paths=_paths(tmp_path),
    )
    async with app.run_test(size=(100, 24)) as pilot:
        assert isinstance(app.screen, ConhostWarningScreen)
        assert getattr(app.screen.focused, "id", None) == "warning-close"
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, ConhostWarningScreen)
        assert getattr(app.focused, "id", None) == "route-home"


async def test_missing_config_is_disclosed_without_opening_runtime(tmp_path: Path) -> None:
    app = MemtomemTuiApp(
        startup_refresh=True,
        terminal_profile="windows-terminal",
        paths=_paths(tmp_path, configured=False),
    )
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        rendered = _rendered_text(app.query_one("#home-surface"))
        assert "SETUP REQUIRED" in rendered
        assert "Setup has not been completed" in rendered
        assert "without creating a database" in rendered


async def test_refresh_rechecks_config_without_rebuilding_home_or_moving_focus(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path, configured=False)
    app = MemtomemTuiApp(
        startup_refresh=True,
        terminal_profile="windows-terminal",
        paths=paths,
    )
    async with app.run_test(size=(100, 24)) as pilot:
        home = app.query_one("#home-surface")
        app.activate_section("main")
        home.focus()

        paths.config_path.write_text("{}\n", encoding="utf-8")
        await pilot.press("ctrl+r")

        assert app.query_one("#home-surface") is home
        assert app.state.active_section == "main"
        assert app.focused is home
        assert "SEARCH DATABASE MISSING" in _rendered_text(home)
        assert "SETUP REQUIRED" not in _rendered_text(home)

        paths.config_path.unlink()
        await pilot.press("ctrl+r")

        assert app.query_one("#home-surface") is home
        assert app.state.active_section == "main"
        assert app.focused is home
        assert "SETUP REQUIRED" in _rendered_text(home)
        assert "Setup has not been completed" in _rendered_text(home)


async def test_refresh_is_guarded_while_a_modal_is_open(tmp_path: Path) -> None:
    paths = _paths(tmp_path, configured=False)
    app = MemtomemTuiApp(
        startup_refresh=True,
        terminal_profile="windows-terminal",
        paths=paths,
    )
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        home = app.query_one("#home-surface")
        assert "SETUP REQUIRED" in _rendered_text(home)

        await pilot.press("ctrl+q")
        paths.config_path.write_text("{}\n", encoding="utf-8")
        await pilot.press("ctrl+r")

        assert isinstance(app.screen, QuitConfirmScreen)
        assert "SETUP REQUIRED" in _rendered_text(home)

        await pilot.press("escape")
        await pilot.press("ctrl+r")
        assert "SEARCH DATABASE MISSING" in _rendered_text(home)


async def test_global_errors_are_structured_and_user_visible(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        notice = ErrorNotice(
            code="TUI-PHASE2",
            message="Example [bold] recoverable shell error",
            detail="private diagnostic detail",
            recoverable=True,
        )
        app.report_error(notice)
        await pilot.pause()
        app.screen.query_one("#global-error").refresh()
        assert app.state.error is notice
        rendered = _rendered_text(app.screen)
        assert "TUI-PHASE2" in rendered
        assert "private diagnostic detail" not in rendered
        banner = app.query_one("#global-error", Static)
        assert "[x]" in banner.render_line(0).text
        assert "[bold]" in banner.render_line(0).text
        assert list(app._notifications)[-1].markup is False


async def test_global_error_remains_visible_across_focused_and_split_layouts(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(59, 16)) as pilot:
        app.report_error(ErrorNotice(code="VISIBLE", message="Keep this error visible"))
        await pilot.pause()
        banner = app.query_one("#global-error", Static)
        assert banner.display
        assert banner.region.height > 0
        assert not app.query_one("#detail").display

        await pilot.resize_terminal(60, 16)
        assert app.state.active_section == "nav"
        assert app.query_one("#detail").display
        assert banner.display
        assert banner.region.height > 0
        assert "VISIBLE" in str(banner.render())


async def test_pointer_click_activates_nearest_focusable_section_owner(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.click("#home-surface")
        assert app.state.active_section == "main"
        assert getattr(app.focused, "id", None) == "home-surface"


async def test_arrows_and_hjkl_never_leave_the_active_panel(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.press("up", "down", "left", "right", "h", "j", "k", "l")
        assert app.state.active_section == "nav"

        await pilot.press("f3", "up", "down", "left", "right", "h", "j", "k", "l")
        assert app.state.active_section == "main"

        await pilot.press("f4", "up", "down", "left", "right", "h", "j", "k", "l")
        assert app.state.active_section == "detail"


async def test_square_brackets_move_panels_without_wrapping(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("left_square_bracket")
        assert app.state.active_section == "nav"

        await pilot.press("right_square_bracket")
        assert app.state.active_section == "main"
        await pilot.press("right_square_bracket")
        assert app.state.active_section == "detail"
        await pilot.press("right_square_bracket")
        assert app.state.active_section == "detail"

        await pilot.press("left_square_bracket", "left_square_bracket")
        assert app.state.active_section == "nav"
        await pilot.press("left_square_bracket")
        assert app.state.active_section == "nav"


async def test_text_input_keeps_printable_navigation_keys(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        surface = app.query_one("#home-surface")
        field = TuiInput(id="navigation-key-input")
        await surface.mount(field)
        app.activate_section("main")
        field.focus()

        await pilot.press(
            "left_square_bracket",
            "h",
            "j",
            "k",
            "l",
            "right_square_bracket",
        )

        assert field.value == "[hjkl]"
        assert app.state.active_section == "main"


async def test_escape_follows_detail_main_navigation_quit_ladder(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("f4", "escape")
        assert app.state.active_section == "main"
        await pilot.press("escape")
        assert app.state.active_section == "nav"
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, QuitConfirmScreen)


async def test_modal_blocks_background_panel_navigation(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("?")
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("f4", "right_square_bracket", "down", "right")
        assert app.state.active_section == "nav"

        await pilot.press("escape")
        await pilot.pause()
        assert app.state.active_section == "nav"


async def test_inactive_remembered_navigation_focus_cannot_activate_route(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        route = app.query_one("#route-home", NavigationItem)
        route.focus()
        app.state.route_id = "sentinel"
        app.state.activate("main")

        await pilot.press("enter")
        assert app.state.route_id == "sentinel"


async def test_escape_from_input_restores_focusable_parent_surface(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        surface = app.query_one("#home-surface")
        field = TuiInput(id="phase2-input")
        await surface.mount(field)
        app.activate_section("main")
        field.focus()

        await pilot.press("escape")
        assert app.focused is surface


async def test_repeated_resize_preserves_input_value_and_remembered_focus(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 24)) as pilot:
        surface = app.query_one("#home-surface")
        field = TuiInput(value="한글 / C:/very/long/path", id="resize-input")
        await surface.mount(field)
        app.activate_section("main")
        field.focus()

        for width, height in ((60, 16), (160, 10), (31, 8), (100, 24)):
            await pilot.resize_terminal(width, height)

        assert field.value == "한글 / C:/very/long/path"
        assert app.state.active_section == "main"
        assert app.focused is field


async def test_panel_button_blocks_stale_keyboard_but_syncs_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        surface = app.query_one("#home-surface")
        button = PanelButton("Run", id="phase2-run")
        await surface.mount(button)
        pressed: list[bool] = []
        monkeypatch.setattr(button, "press", lambda: pressed.append(True))
        button.focus()
        app.state.activate("nav")

        await pilot.press("enter")
        assert pressed == []

        await pilot.click("#phase2-run")
        assert app.state.active_section == "main"
        assert pressed == [True]


async def test_ascii_active_section_keeps_focus_border_color(tmp_path: Path) -> None:
    app = _app(tmp_path, border_style="ascii")
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("f3")
        main = app.query_one("#main")
        assert main.styles.border_top[0] == "ascii"
        assert main.styles.border_top[1].hex == "#00DDDD"

        await pilot.resize_terminal(59, 16)
        await pilot.press("f2")
        navigation = app.query_one("#navigation")
        assert navigation.styles.border_top[0] == "ascii"
        assert navigation.styles.border_top[1].hex == "#00DDDD"


def test_styles_are_layered_and_do_not_style_individual_buttons_by_id() -> None:
    styles = Path(__file__).parents[1] / "src" / "memtomem" / "tui" / "styles"
    assert {path.name for path in styles.glob("*.tcss")} == {
        "tokens.tcss",
        "layout.tcss",
        "components.tcss",
        "states.tcss",
        "responsive.tcss",
    }
    css = "\n".join(path.read_text(encoding="utf-8") for path in styles.glob("*.tcss"))
    assert "#quit-yes {" not in css
    assert "#quit-no {" not in css
    assert "#route-home {" not in css
    assert "Button.cyan" in css
    assert ".nav-item:disabled" in css
    assert MemtomemTuiApp.CSS.index("$surface-lowest:") < MemtomemTuiApp.CSS.index(
        "background: $surface-lowest"
    )


async def test_tui_input_copy_cut_and_paste_use_os_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        "memtomem.tui.clipboard.write_os_clipboard",
        lambda text: copied.append(text) or True,
    )
    monkeypatch.setattr("memtomem.tui.clipboard.read_os_clipboard", lambda: "붙여넣기")
    app = _InputTestApp()
    async with app.run_test():
        widget = app.query_one("#test-input", TuiInput)
        widget.selection = (1, 4)
        widget.action_copy()
        assert copied == ["bcd"]
        widget.action_cut()
        assert widget.value == "aef"
        assert widget.cursor_position == 1
        widget.action_paste()
        assert widget.value == "a붙여넣기ef"
