"""Tests for the ``mm tui`` entry point and command catalog."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from click.testing import CliRunner
from textual.widgets import Button, Footer, Input, ListItem, ListView, SelectionList, Static, Tabs
from textual.widgets._input import Selection

from memtomem.cli import cli
from memtomem.models import Chunk, ChunkMetadata, SearchResult
from memtomem.tui import clipboard as tui_clipboard
from memtomem.tui.app import (
    ConhostWarningScreen,
    InputDiagnosticsApp,
    KeybindingsScreen,
    ManagedRootsSelectionList,
    MemtomemTuiApp,
    MenuItem,
    ModalButton,
    QuitConfirmScreen,
    RootSelectionAction,
    SettingRow,
    SettingStep,
)
from memtomem.tui import runtime
from memtomem.tui.catalog import COMMAND_CATALOG
from memtomem.tui.runtime import ReadinessState
from memtomem.tui.shared import PanelScroll
from memtomem.tui.terminal import choose_border_style, detect_terminal_profile


def make_tui_app(*, border_style: str = "solid") -> MemtomemTuiApp:
    return MemtomemTuiApp(
        border_style=border_style,
        startup_refresh=False,
        terminal_profile="windows-terminal",
        mouse_enabled=True,
    )


class FakeClick:
    stopped = False

    def stop(self) -> None:
        self.stopped = True


def test_tui_in_top_level_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.output


def test_tui_help_does_not_require_textual() -> None:
    result = CliRunner().invoke(cli, ["tui", "--help"])

    assert result.exit_code == 0
    assert "terminal UI" in result.output
    assert "--border" in result.output
    assert "--diagnose-terminal" in result.output
    assert "--diagnose-input" in result.output
    assert "--mouse / --no-mouse" in result.output


def test_tui_missing_textual_has_install_hint(monkeypatch) -> None:
    monkeypatch.setattr(
        "importlib.util.find_spec", lambda name: None if name == "textual" else None
    )

    result = CliRunner().invoke(cli, ["tui"])

    assert result.exit_code == 1
    assert "requires the [tui] extra" in result.output
    assert "memtomem[tui]" in result.output


def test_tui_diagnose_terminal_does_not_require_textual(monkeypatch) -> None:
    monkeypatch.setattr(
        "importlib.util.find_spec", lambda name: None if name == "textual" else None
    )

    result = CliRunner().invoke(cli, ["tui", "--diagnose-terminal"])

    assert result.exit_code == 0
    assert "memtomem TUI Terminal Diagnostics" in result.output
    assert "Rendering probes" in result.output
    assert "Plain Unicode box drawing" in result.output
    assert "ANSI-colored Unicode box drawing" in result.output
    assert "Adjacent colored panels" in result.output
    assert "ASCII fallback" in result.output
    assert "Interpretation" in result.output


def test_tui_launch_passes_mouse_option(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr("memtomem.tui.terminal.detect_terminal_profile", lambda: "windows-terminal")
    monkeypatch.setattr("memtomem.tui.app.run", lambda **kwargs: calls.append(("run", kwargs)))

    result = CliRunner().invoke(cli, ["tui", "--border", "ascii", "--no-mouse"])

    assert result.exit_code == 0
    assert calls == [
        (
            "run",
            {"border_style": "ascii", "mouse": False, "terminal_profile": "windows-terminal"},
        )
    ]


def test_tui_input_diagnostics_uses_textual_app(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr("memtomem.tui.terminal.detect_terminal_profile", lambda: "windows-terminal")
    monkeypatch.setattr(
        "memtomem.tui.app.run_input_diagnostics",
        lambda **kwargs: calls.append(("diagnose", kwargs)),
    )

    result = CliRunner().invoke(cli, ["tui", "--diagnose-input", "--border", "solid", "--no-mouse"])

    assert result.exit_code == 0
    assert calls == [
        (
            "diagnose",
            {"border_style": "solid", "mouse": False, "terminal_profile": "windows-terminal"},
        )
    ]


def test_terminal_border_auto_detection() -> None:
    assert detect_terminal_profile({"WT_SESSION": "abc"}, os_name="nt") == "windows-terminal"
    assert choose_border_style("auto", {"WT_SESSION": "abc"}, os_name="nt") == "solid"
    assert choose_border_style("auto", {}, os_name="nt") == "ascii"
    assert choose_border_style("auto", {"TERM_PROGRAM": "vscode"}, os_name="nt") == "solid"
    assert choose_border_style("auto", {"MEMTOMEM_TUI_BORDER": "ascii"}, os_name="posix") == "ascii"
    assert choose_border_style("solid", {"MEMTOMEM_TUI_BORDER": "ascii"}, os_name="nt") == "solid"


def test_windows_clipboard_write_reads_stdin_explicitly(monkeypatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tui_clipboard.os, "name", "nt")
    monkeypatch.setattr(tui_clipboard.shutil, "which", lambda command: f"C:/{command}")
    monkeypatch.setattr(tui_clipboard.subprocess, "run", fake_run)

    assert tui_clipboard.write_os_clipboard("copied text")

    assert calls == [
        (
            [
                "C:/powershell.exe",
                "-NoProfile",
                "-Command",
                "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
            ],
            {
                "capture_output": True,
                "check": False,
                "input": "copied text",
                "text": True,
                "timeout": 2,
            },
        )
    ]


async def test_tui_search_warns_about_conhost_ime_limitations() -> None:
    app = MemtomemTuiApp(startup_refresh=False, terminal_profile="windows-conhost")

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()

        warnings = [
            widget.content for widget in app.query("#main-body .warning").results(Static)
        ]
        assert any("Korean IME input is limited" in warning for warning in warnings)


async def test_tui_shows_conhost_startup_warning() -> None:
    app = MemtomemTuiApp(startup_refresh=False, terminal_profile="windows-conhost")

    async with app.run_test() as pilot:
        await pilot.pause()

        assert isinstance(app.screen, ConhostWarningScreen)
        body = app.screen.query_one("#conhost-warning-body", Static).content
        assert "Windows Terminal is strongly recommended" in body


async def test_tui_does_not_show_conhost_warning_in_windows_terminal() -> None:
    app = MemtomemTuiApp(startup_refresh=False, terminal_profile="windows-terminal")

    async with app.run_test() as pilot:
        await pilot.pause()

        assert not isinstance(app.screen, ConhostWarningScreen)


async def test_tui_mouse_mode_toggle_updates_status(monkeypatch) -> None:
    calls = []
    app = make_tui_app()
    monkeypatch.setattr(app, "_write_mouse_sequence", lambda enabled: calls.append(enabled))

    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.query_one("#mouse-status", Static).content == "Mouse:TUI"
        await pilot.press("f6")
        assert app.query_one("#mouse-status", Static).content == "Mouse:OS"
        await pilot.press("f6")
        assert app.query_one("#mouse-status", Static).content == "Mouse:TUI"

    assert calls == [False, True]


async def test_tui_mouse_mode_toggle_works_from_input_focus(monkeypatch) -> None:
    calls = []
    app = make_tui_app()
    monkeypatch.setattr(app, "_write_mouse_sequence", lambda enabled: calls.append(enabled))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        query = app.query_one("#search-query")
        query.focus()

        await pilot.press("f6")

        assert query.value == ""
        assert app.query_one("#mouse-status", Static).content == "Mouse:OS"

    assert calls == [False]


async def test_tui_alt_m_mouse_mode_toggle_still_works(monkeypatch) -> None:
    calls = []
    app = make_tui_app()
    monkeypatch.setattr(app, "_write_mouse_sequence", lambda enabled: calls.append(enabled))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("alt+m")

        assert app.query_one("#mouse-status", Static).content == "Mouse:OS"

    assert calls == [False]


async def test_tui_input_diagnostics_warns_about_conhost_ime_limitations() -> None:
    app = InputDiagnosticsApp(terminal_profile="windows-conhost")

    async with app.run_test() as pilot:
        await pilot.pause()

        warnings = [
            widget.content for widget in app.query("#diagnostics .warning").results(Static)
        ]
        assert any("Korean IME input is limited" in warning for warning in warnings)


def test_tui_catalog_covers_top_level_commands() -> None:
    catalog = {entry.command for entry in COMMAND_CATALOG}
    expected = {
        "mm activity",
        "mm add",
        "mm agent",
        "mm config",
        "mm context",
        "mm embedding-reset",
        "mm gc",
        "mm index",
        "mm ingest",
        "mm init",
        "mm mem",
        "mm memory doctor",
        "mm purge",
        "mm recall",
        "mm reset",
        "mm schedule",
        "mm search",
        "mm session",
        "mm shell",
        "mm status",
        "mm sync-doctor",
        "mm tags",
        "mm uninstall",
        "mm upgrade",
        "mm version",
        "mm watchdog",
        "mm web",
        "mm wiki",
    }

    missing = expected - catalog
    assert not missing


async def test_tui_catalog_assigns_scroll_to_list_until_minimum_height() -> None:
    async def measure(size: tuple[int, int]) -> tuple[bool, int, bool]:
        app = make_tui_app()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            app.render_catalog()
            await pilot.pause()
            body = app.query_one("#main-body", PanelScroll)
            command_list = app.query_one(".command-list", ListView)
            return (
                body.show_vertical_scrollbar,
                command_list.size.height,
                command_list.show_vertical_scrollbar,
            )

    normal_body_scroll, normal_list_height, normal_list_scroll = await measure((120, 30))
    assert not normal_body_scroll
    assert normal_list_height > 1
    assert normal_list_scroll

    short_body_scroll, short_list_height, short_list_scroll = await measure((120, 15))
    assert not short_body_scroll
    assert short_list_height == 1
    assert short_list_scroll

    extreme_body_scroll, extreme_list_height, _ = await measure((120, 12))
    assert extreme_body_scroll
    assert extreme_list_height == 1


def test_init_flow_definition_uses_canonical_presets() -> None:
    from memtomem.cli.init_cmd import get_init_flow_definition
    from memtomem.cli.init_presets import PRESETS

    flow = get_init_flow_definition()

    assert [p.name for p in flow.presets] == ["minimal", "english", "korean"]
    assert [p.label for p in flow.presets] == [
        PRESETS["minimal"].label,
        PRESETS["english"].label,
        PRESETS["korean"].label,
    ]
    assert flow.interactive_default_preset == "english"
    assert flow.non_interactive_default_preset == "minimal"
    assert len(flow.advanced_step_titles) == 10
    assert flow.advanced_step_titles[0] == "Embedding Provider"
    assert flow.advanced_step_titles[-1] == "Connect to AI Editor"


def test_count_indexable_files(tmp_path) -> None:
    root = tmp_path / "memories"
    root.mkdir()
    (root / "one.md").write_text("# One", encoding="utf-8")
    (root / "skip.bin").write_bytes(b"\0")
    nested = root / "nested"
    nested.mkdir()
    (nested / "two.json").write_text("{}", encoding="utf-8")

    assert runtime.count_indexable_files((root,), {".md", ".json"}) == 2


async def test_inspect_readiness_flags_index_required(tmp_path) -> None:
    class Storage:
        async def get_stats(self):
            return {"total_chunks": 0, "total_sources": 0}

    root = tmp_path / "memories"
    root.mkdir()
    (root / "note.md").write_text("# Note", encoding="utf-8")

    config = type(
        "Config",
        (),
        {
            "indexing": type(
                "Indexing",
                (),
                {
                    "memory_dirs": [root],
                    "supported_extensions": {".md"},
                },
            )()
        },
    )()
    comp = type("Components", (), {"config": config, "storage": Storage()})()

    readiness = await runtime.inspect_readiness(comp)

    assert readiness.state == ReadinessState.INDEX_REQUIRED
    assert readiness.indexable_files == 1


async def test_tui_vertical_navigation_moves_within_active_panel() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        await app._replace_main(  # noqa: SLF001 - focused TUI interaction test.
            Button("One", id="main-one"),
            Button("Two", id="main-two"),
        )
        app.focus_panel(0)

        await pilot.press("down")
        assert app.PANEL_IDS[app.panel_index] == "main"
        assert getattr(app.focused, "id", None) == "main-one"
        await pilot.press("up")
        assert app.PANEL_IDS[app.panel_index] == "menu"
        await pilot.press("down")
        assert app.PANEL_IDS[app.panel_index] == "main"
        assert getattr(app.focused, "id", None) == "main-one"

        app.query_one("#main-one", Button).focus()
        await pilot.press("down")
        assert getattr(app.focused, "id", None) == "main-two"

        await pilot.press("up")
        assert getattr(app.focused, "id", None) == "main-one"
        await pilot.press("right")
        assert app.PANEL_IDS[app.panel_index] == "detail"
        await pilot.press("left")
        assert app.PANEL_IDS[app.panel_index] == "main"
        assert getattr(app.focused, "id", None) == "main-one"

        app.render_catalog()
        await pilot.pause()
        app.focus_panel(0)
        await pilot.press("f3")
        assert app.PANEL_IDS[app.panel_index] == "main"

        catalog = app.query_one("#main-body ListView", ListView)
        catalog.focus()
        catalog.index = 0
        await pilot.press("down")
        assert catalog.index == 1

        await pilot.press("f2")
        assert app.PANEL_IDS[app.panel_index] == "menu"
        await pilot.press("f4")
        assert app.PANEL_IDS[app.panel_index] == "detail"


async def test_tui_ascii_border_class_is_applied() -> None:
    app = make_tui_app(border_style="ascii")

    async with app.run_test() as pilot:
        await pilot.pause()

        assert not app.query_one("#menu-bar").has_class("ascii-border")
        assert app.query_one("#main").has_class("ascii-border")
        assert app.query_one("#detail").has_class("ascii-border")


async def test_tui_help_uses_selected_border_style() -> None:
    app = make_tui_app(border_style="ascii")

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("?")

        assert isinstance(app.screen, KeybindingsScreen)
        assert app.screen.query_one("#keybindings-dialog").has_class("ascii-border")


async def test_tui_settings_controls_footer_offset() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        assert app.query_one("#footer-height-value", Static).content == "0"
        assert app.query_one("#footer-height-decrease", SettingStep).content == "v"
        assert app.query_one("#footer-height-increase", SettingStep).content == "^"
        assert getattr(app.focused, "id", None) == "nav-settings"
        assert not app.query_one("#footer-height-setting", SettingRow).has_class("active-nav")
        assert app.query_one(Footer).styles.margin.bottom == 0

        await app.handle_button("footer-height-increase")
        assert app.footer_offset == 1
        assert app.query_one("#footer-height-value", Static).content == "1"
        assert app.query_one(Footer).styles.margin.bottom == 1

        await app.handle_button("footer-height-decrease")
        assert app.footer_offset == 0
        assert app.query_one("#footer-height-value", Static).content == "0"
        assert app.query_one(Footer).styles.margin.bottom == 0


async def test_tui_navigation_activation_does_not_move_focus() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))

        await pilot.press("enter")
        await pilot.pause()

        assert app.current_page_id == "settings"
        assert getattr(app.focused, "id", None) == "nav-settings"
        assert app.PANEL_IDS[app.panel_index] == "menu"


async def test_tui_menu_focus_keeps_label_with_cyan_focus_style() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-search"))
        await pilot.pause()

        item = app.query_one("#nav-search", MenuItem)

        assert item.content == "Search"
        assert item.styles.background.hex == "#45E0FF"
        assert item.styles.color.hex == "#0D141C"


async def test_tui_settings_keyboard_edit_applies_and_cancels_footer_height() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        assert getattr(app.focused, "id", None) == "nav-settings"
        await pilot.press("right")
        await pilot.press("down")
        assert getattr(app.focused, "id", None) == "footer-height-setting"

        await pilot.press("enter")
        assert app.settings_editing is True
        assert app.query_one("#footer-height-setting", SettingRow).has_class("editing-setting")
        assert app.query_one("#footer-height-value", Static).has_class("editing-setting")

        await pilot.press("up")
        assert app.footer_offset == 0
        assert app.query_one("#footer-height-value", Static).content == "1"
        assert app.query_one(Footer).styles.margin.bottom == 0

        await pilot.press("enter")
        assert app.settings_editing is False
        assert app.footer_offset == 1
        assert app.query_one(Footer).styles.margin.bottom == 1
        assert not app.query_one("#footer-height-value", Static).has_class("editing-setting")

        await pilot.press("enter")
        await pilot.press("up")
        assert app.query_one("#footer-height-value", Static).content == "2"
        await pilot.press("escape")

        assert app.settings_editing is False
        assert app.footer_offset == 1
        assert app.query_one("#footer-height-value", Static).content == "1"
        assert app.query_one(Footer).styles.margin.bottom == 1


async def test_tui_enter_on_panel_focus_does_nothing() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        main_body = app.query_one("#main-body")
        app.set_focus(main_body)
        app.panel_index = app.PANEL_IDS.index("main")
        app.set_active_panel("main")

        await pilot.press("enter")
        await pilot.pause()

        assert app.current_page_id == "settings"
        assert app.focused is main_body
        assert app.PANEL_IDS[app.panel_index] == "main"


async def test_tui_enter_ignores_stale_focus_from_inactive_panel() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        app.query_one("#nav-dashboard", MenuItem).focus()
        app.panel_index = app.PANEL_IDS.index("main")
        app.set_active_panel("main")

        await pilot.press("enter")
        await pilot.pause()

        assert app.current_page_id == "settings"
        assert getattr(app.focused, "id", None) == "nav-dashboard"
        assert app.PANEL_IDS[app.panel_index] == "main"


async def test_tui_settings_editing_blocks_panel_left_right() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        await pilot.press("right")
        await pilot.press("down")
        await pilot.press("enter")
        assert app.settings_editing is True
        assert app.PANEL_IDS[app.panel_index] == "main"

        await pilot.press("left")
        await pilot.press("right")

        assert app.PANEL_IDS[app.panel_index] == "main"
        assert getattr(app.focused, "id", None) == "footer-height-setting"


async def test_tui_settings_row_click_focuses_setting() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        await pilot.click("#footer-height-setting")
        await pilot.pause()

        assert getattr(app.focused, "id", None) == "footer-height-setting"
        assert app.PANEL_IDS[app.panel_index] == "main"
        assert app.query_one("#footer-height-setting", SettingRow).has_class("active-nav")

        await pilot.press("enter")
        assert app.settings_editing is True


async def test_tui_settings_edit_mouse_click_cancels_without_applying() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        app.focus_settings_item()
        await pilot.press("enter")
        await pilot.press("up")

        assert app.settings_editing is True
        assert app.footer_offset == 0
        assert app.query_one("#footer-height-value", Static).content == "1"

        await pilot.click("#footer-height-increase")
        await pilot.pause()

        assert app.settings_editing is False
        assert app.footer_offset == 0
        assert app.query_one("#footer-height-value", Static).content == "0"


async def test_tui_settings_edit_panel_button_click_cancels_without_running() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        app.focus_settings_item()
        await pilot.press("enter")
        await pilot.press("up")
        button = app.query_one("#nav-search", MenuItem)
        event = FakeClick()

        await button._on_click(event)
        await pilot.pause()

        assert event.stopped is True
        assert app.settings_editing is False
        assert app.current_page_id == "settings"
        assert app.footer_offset == 0
        assert app.query_one("#footer-height-value", Static).content == "0"


async def test_tui_mouse_click_syncs_panel_before_button_action() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-settings"))
        await app.handle_button("nav-settings")
        await pilot.pause()

        setting = app.query_one("#footer-height-setting", SettingRow)
        setting.focus()
        app.panel_index = app.PANEL_IDS.index("main")
        app.set_active_panel("main")

        button = app.query_one("#nav-search", MenuItem)
        event = FakeClick()

        await button._on_click(event)
        await pilot.pause()

        assert event.stopped is True
        assert app.current_page_id == "search"
        assert getattr(app.focused, "id", None) == "nav-search"
        assert app.PANEL_IDS[app.panel_index] == "menu"


async def test_tui_escape_moves_widget_focus_to_panel() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        search_input = app.query_one("#search-query", Input)
        search_input.focus()

        await pilot.press("escape")

        assert app.focused is app.query_one("#main-body")
        assert not isinstance(app.screen, QuitConfirmScreen)


async def test_tui_escape_on_panel_moves_to_menu_before_quit_confirmation() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_panel(1)
        app.set_focus(app.query_one("#main-body"))

        await pilot.press("escape")
        await pilot.pause()

        assert app.PANEL_IDS[app.panel_index] == "menu"
        assert getattr(app.focused, "id", None) == "nav-dashboard"
        assert not isinstance(app.screen, QuitConfirmScreen)

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, QuitConfirmScreen)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, QuitConfirmScreen)


async def test_tui_ctrl_q_opens_quit_confirmation() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("ctrl+q")
        await pilot.pause()

        assert isinstance(app.screen, QuitConfirmScreen)

        await pilot.press("escape")


async def test_tui_quit_confirmation_enter_uses_focused_button() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("ctrl+q")
        await pilot.pause()

        assert isinstance(app.screen, QuitConfirmScreen)
        assert getattr(app.screen.focused, "id", None) == "cancel-quit"
        assert isinstance(app.screen.query_one("#cancel-quit", Button), ModalButton)
        assert app.screen.query_one("#cancel-quit", Button).has_class("cyan")
        assert not app.screen.query_one("#confirm-quit", Button).has_class("cyan")

        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, QuitConfirmScreen)


async def test_tui_quit_confirmation_arrow_keys_move_button_focus() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("ctrl+q")
        await pilot.pause()

        assert isinstance(app.screen, QuitConfirmScreen)
        assert getattr(app.screen.focused, "id", None) == "cancel-quit"

        await pilot.press("left")
        assert getattr(app.screen.focused, "id", None) == "confirm-quit"
        assert app.screen.query_one("#confirm-quit", Button).has_class("cyan")
        assert not app.screen.query_one("#cancel-quit", Button).has_class("cyan")

        await pilot.press("right")
        assert getattr(app.screen.focused, "id", None) == "cancel-quit"
        assert app.screen.query_one("#cancel-quit", Button).has_class("cyan")
        assert not app.screen.query_one("#confirm-quit", Button).has_class("cyan")

        await pilot.press("escape")


async def test_tui_quit_confirmation_tab_updates_button_style() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("ctrl+q")
        await pilot.pause()

        assert isinstance(app.screen, QuitConfirmScreen)
        await pilot.press("shift+tab")
        await pilot.pause()

        assert getattr(app.screen.focused, "id", None) == "confirm-quit"
        assert app.screen.query_one("#confirm-quit", Button).has_class("cyan")
        assert not app.screen.query_one("#cancel-quit", Button).has_class("cyan")

        await pilot.press("escape")


async def test_tui_page_keys_scroll_main_body() -> None:
    app = make_tui_app()

    async with app.run_test(size=(100, 16)) as pilot:
        await pilot.pause()
        await app._replace_main(  # noqa: SLF001 - focused TUI interaction test.
            *[Static(f"Line {index}") for index in range(40)]
        )
        app.focus_panel(1)
        body = app.query_one("#main-body")

        assert body.scroll_y == 0
        await pilot.press("page_down")
        assert body.scroll_y > 0

        await pilot.press("page_up")
        assert body.scroll_y == 0


async def test_tui_arrow_keys_do_not_scroll_panel_body() -> None:
    app = make_tui_app()

    async with app.run_test(size=(100, 16)) as pilot:
        await pilot.pause()
        await app._replace_main(  # noqa: SLF001 - focused TUI interaction test.
            *[Static(f"Line {index}") for index in range(40)]
        )
        app.focus_panel(1)
        await pilot.pause()
        body = app.query_one("#main-body")

        assert body.scroll_y == 0
        await pilot.press("down")
        await pilot.press("j")
        assert body.scroll_y == 0

        await pilot.press("page_down")
        assert body.scroll_y > 0


async def test_tui_page_keys_move_list_view_by_page() -> None:
    app = make_tui_app()

    async with app.run_test(size=(100, 16)) as pilot:
        await pilot.pause()
        list_view = ListView(*[ListItem(Static(f"Item {index}")) for index in range(40)])
        await app._replace_main(list_view)  # noqa: SLF001 - focused TUI interaction test.
        await pilot.pause()
        app.focus_panel(1)
        await pilot.pause()
        app.set_focus(list_view)

        assert isinstance(app.focused, ListView)
        app.focused.index = 0
        await pilot.press("page_down")

        assert app.focused.index is not None
        assert app.focused.index > 0


async def test_tui_page_keys_scroll_detail_panel() -> None:
    app = make_tui_app()

    async with app.run_test(size=(100, 16)) as pilot:
        await pilot.pause()
        detail_text = app.query_one("#detail-text", Static)
        detail_text.update("\n".join(f"Detail line {index}" for index in range(40)))
        app.focus_panel(2)
        await pilot.pause()
        detail_body = app.query_one("#detail-body")

        assert detail_body.scroll_y == 0
        await pilot.press("page_down")
        assert detail_body.scroll_y > 0


async def test_tui_page_keys_scroll_help_modal() -> None:
    app = make_tui_app()

    async with app.run_test(size=(80, 10)) as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(app.screen, KeybindingsScreen)
        help_body = app.screen.query_one("#keybindings-body-scroll")

        assert help_body.scroll_y == 0
        await pilot.press("page_down")
        assert help_body.scroll_y > 0


async def test_tui_search_screen_runs_pipeline() -> None:
    class SearchPipeline:
        def __init__(self) -> None:
            self.query = None

        async def search(self, query, **kwargs):
            self.query = query
            chunk = Chunk(
                id=uuid4(),
                content="Searchable content for the terminal UI.",
                metadata=ChunkMetadata(
                    source_file="notes/search.md",
                    heading_hierarchy=("Search", "TUI"),
                    tags=("tui",),
                    namespace="user",
                ),
            )
            result = SearchResult(chunk=chunk, score=0.75, rank=1, source="bm25")
            stats = SimpleNamespace(bm25_candidates=1, dense_candidates=0, final_total=1)
            return [result], stats

    pipeline = SearchPipeline()
    config = SimpleNamespace(indexing=SimpleNamespace(project_memory_dirs=[]))
    app = make_tui_app()
    app.comp = SimpleNamespace(search_pipeline=pipeline, config=config)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        query = app.query_one("#search-query")
        query.value = "terminal ui"
        await app.run_search_from_input()
        await pilot.pause()

        assert pipeline.query == "terminal ui"
        assert len(app.search_results) == 1
        assert "notes/search.md" in app.query_one("#detail-text", Static).content


async def test_tui_index_overview_shows_dense_coverage() -> None:
    class Storage:
        async def get_stats(self):
            return {"total_chunks": 10, "total_sources": 2}

        async def get_dense_coverage(self):
            return {"total": 10, "with_dense": 8}

        async def get_all_source_files(self):
            return set()

    app = make_tui_app()
    app.comp = SimpleNamespace(storage=Storage())

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_index("overview")
        await pilot.pause()

        main_text = "\n".join(
            str(widget.content) for widget in app.query("#main-body Static").results(Static)
        )
        assert "Dense vectors: 8/10 (80.0%)" in main_text
        assert "semantic-search embeddings" in app.query_one("#detail-text", Static).content


async def test_tui_managed_roots_uses_selection_list(tmp_path) -> None:
    class Storage:
        async def get_source_files_with_counts(self):
            return []

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    class Indexing:
        memory_dirs = [root_a, root_b]
        supported_extensions = frozenset({".md"})

        def all_index_roots(self):
            return self.memory_dirs

    app = make_tui_app()
    app.comp = SimpleNamespace(storage=Storage(), config=SimpleNamespace(indexing=Indexing()))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.render_index("roots")
        await pilot.pause()

        root_list = app.query_one("#root-list", ManagedRootsSelectionList)
        assert root_list.option_count == 2
        assert root_list.size.height > 0
        assert root_list.highlighted == 0
        assert root_list.render_line(0).text.startswith("[ ]")

        app.focus_panel(1)
        root_list.focus()
        await pilot.press("space")
        assert root_list.render_line(0).text.startswith("[*]")
        await pilot.press("enter")
        assert root_list.render_line(0).text.startswith("[ ]")
        await pilot.press("enter")
        assert root_list.render_line(0).text.startswith("[*]")
        await pilot.press("down")
        await pilot.press("space")

        assert root_list.selected == [str(root_a.resolve()), str(root_b.resolve())]


async def test_tui_managed_roots_selection_toolbar(tmp_path) -> None:
    class Storage:
        async def get_source_files_with_counts(self):
            return []

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    class Indexing:
        memory_dirs = [root_a, root_b]
        supported_extensions = frozenset({".md"})

        def all_index_roots(self):
            return self.memory_dirs

    app = make_tui_app()
    app.comp = SimpleNamespace(storage=Storage(), config=SimpleNamespace(indexing=Indexing()))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_index("roots")
        await pilot.pause()

        root_list = app.query_one("#root-list", ManagedRootsSelectionList)
        assert app.query_one("#select-all-roots", RootSelectionAction).content == "*"
        assert app.query_one("#deselect-all-roots", RootSelectionAction).content == "-"
        assert app.query_one("#toggle-all-roots", RootSelectionAction).content == "~"
        assert "root-selection-label" not in {widget.id for widget in app.query("*")}
        assert "* selects all roots" in app.query_one("#detail-text", Static).content

        await app.handle_button("select-all-roots")
        assert root_list.selected == [str(root_a.resolve()), str(root_b.resolve())]

        await app.handle_button("deselect-all-roots")
        assert root_list.selected == []

        root_list.select(str(root_a.resolve()))
        await app.handle_button("toggle-all-roots")
        assert root_list.selected == [str(root_b.resolve())]


async def test_tui_managed_roots_selection_tokens_are_interactive(tmp_path) -> None:
    class Storage:
        async def get_source_files_with_counts(self):
            return []

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    class Indexing:
        memory_dirs = [root_a, root_b]
        supported_extensions = frozenset({".md"})

        def all_index_roots(self):
            return self.memory_dirs

    app = make_tui_app()
    app.comp = SimpleNamespace(storage=Storage(), config=SimpleNamespace(indexing=Indexing()))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_index("roots")
        await pilot.pause()

        root_list = app.query_one("#root-list", ManagedRootsSelectionList)

        await pilot.click("#select-all-roots")
        await pilot.pause()
        assert root_list.selected == [str(root_a.resolve()), str(root_b.resolve())]
        assert getattr(app.focused, "id", None) == "select-all-roots"

        await pilot.press("right")
        assert getattr(app.focused, "id", None) == "deselect-all-roots"
        await pilot.press("right")
        assert getattr(app.focused, "id", None) == "toggle-all-roots"
        await pilot.press("left")
        assert getattr(app.focused, "id", None) == "deselect-all-roots"
        await pilot.press("down")
        assert getattr(app.focused, "id", None) == "add-root-path"
        await pilot.press("up")
        assert getattr(app.focused, "id", None) == "select-all-roots"

        app.query_one("#deselect-all-roots", RootSelectionAction).focus()
        await pilot.press("enter")
        assert root_list.selected == []


async def test_tui_managed_roots_buttons_move_vertically_in_nearest_order(tmp_path) -> None:
    class Storage:
        async def get_source_files_with_counts(self):
            return []

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    class Indexing:
        memory_dirs = [root_a, root_b]
        supported_extensions = frozenset({".md"})

        def all_index_roots(self):
            return self.memory_dirs

    app = make_tui_app()
    app.comp = SimpleNamespace(storage=Storage(), config=SimpleNamespace(indexing=Indexing()))

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        app.render_index("roots")
        await pilot.pause()

        app.focus_panel_by_id("main", target_id="add-root")
        await pilot.press("down")
        assert getattr(app.focused, "id", None) == "reindex-selected-root"

        await pilot.press("down")
        assert getattr(app.focused, "id", None) == "force-reindex-selected-root"

        await pilot.press("up")
        assert getattr(app.focused, "id", None) == "reindex-selected-root"


async def test_tui_reindex_runs_for_selected_roots(tmp_path) -> None:
    class Storage:
        async def get_source_files_with_counts(self):
            return []

        async def get_stats(self):
            return {"total_chunks": 1, "total_sources": 1}

    class IndexEngine:
        def __init__(self) -> None:
            self.paths = []

        async def index_path_stream(self, path, **kwargs):
            self.paths.append((path, kwargs))
            yield {
                "type": "complete",
                "indexed_chunks": 0,
                "skipped_chunks": 0,
                "deleted_chunks": 0,
            }

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    class Indexing:
        memory_dirs = [root_a, root_b]
        supported_extensions = frozenset({".md"})

        def all_index_roots(self):
            return self.memory_dirs

    engine = IndexEngine()
    app = make_tui_app()
    app.comp = SimpleNamespace(
        index_engine=engine,
        storage=Storage(),
        config=SimpleNamespace(indexing=Indexing()),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_index("roots")
        await pilot.pause()

        root_list = app.query_one("#root-list", SelectionList)
        root_list.select(str(root_a.resolve()))
        root_list.select(str(root_b.resolve()))

        await app.reindex_selected_root(force=False)

        assert [path for path, _kwargs in engine.paths] == [root_a.resolve(), root_b.resolve()]
        assert all(kwargs["recursive"] is True for _path, kwargs in engine.paths)
        assert all(kwargs["force"] is False for _path, kwargs in engine.paths)


async def test_tui_removes_selected_root_and_its_chunks(tmp_path, monkeypatch) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    source_a = root_a / "a.md"
    source_b = root_b / "b.md"
    root_a.mkdir()
    root_b.mkdir()

    class Storage:
        def __init__(self) -> None:
            self.deleted_sources = []

        async def get_source_files_with_counts(self):
            return [(source_a, 2, None), (source_b, 3, None)]

        async def delete_by_source(self, source_path):
            self.deleted_sources.append(source_path)
            return 2

    class Indexing:
        memory_dirs = [root_a, root_b]
        supported_extensions = frozenset({".md"})

        def all_index_roots(self):
            return self.memory_dirs

    storage = Storage()
    config = SimpleNamespace(indexing=Indexing())
    saved_configs = []
    app = make_tui_app()
    app.comp = SimpleNamespace(storage=storage, config=config)
    monkeypatch.setattr(
        "memtomem.config.save_config_overrides", lambda saved: saved_configs.append(saved)
    )

    async def keep_test_components() -> None:
        return None

    monkeypatch.setattr(app, "refresh_readiness", keep_test_components)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_index("roots")
        await pilot.pause()
        monkeypatch.setattr(app, "render_index", lambda _section: None)

        root_list = app.query_one("#root-list", SelectionList)
        root_list.select(str(root_a.resolve()))

        await app.remove_selected_root(delete_chunks=True)

        assert config.indexing.memory_dirs == [root_b]
        assert saved_configs == [config]
        assert storage.deleted_sources == [source_a]
        assert "Deleted chunks: 2" in app.query_one("#detail-text", Static).content


async def test_tui_one_time_index_uses_stream_without_memory_dirs(tmp_path) -> None:
    class IndexEngine:
        def __init__(self) -> None:
            self.path = None

        async def index_path_stream(self, path, **kwargs):
            self.path = path
            yield {"type": "discovery", "files_total": 1}
            yield {
                "type": "progress",
                "files_done": 1,
                "indexed": 2,
                "skipped": 0,
                "file": str(path),
            }
            yield {
                "type": "complete",
                "total_files": 1,
                "indexed_chunks": 2,
                "skipped_chunks": 0,
                "deleted_chunks": 0,
                "errors": [],
            }

    class Storage:
        async def get_stats(self):
            return {"total_chunks": 2, "total_sources": 1}

    target = tmp_path / "outside"
    target.mkdir()
    engine = IndexEngine()
    app = make_tui_app()
    app.comp = SimpleNamespace(
        index_engine=engine,
        storage=Storage(),
        config=SimpleNamespace(
            indexing=SimpleNamespace(
                memory_dirs=[tmp_path / "managed"], supported_extensions={".md"}
            )
        ),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_index("one-time")
        await pilot.pause()
        app.query_one("#one-time-index-path").value = str(target)
        await app.index_one_time_path()
        await pilot.pause()

        assert engine.path == target.resolve()
        assert "Indexing complete." in app.query_one("#index-log", Static).content


async def test_tui_f_keys_move_active_index_tabs_from_input_focus() -> None:
    class Storage:
        async def get_stats(self):
            return {"total_chunks": 0, "total_sources": 0}

        async def get_dense_coverage(self):
            return {"total": 0, "with_dense": 0}

        async def get_all_source_files(self):
            return set()

        async def get_source_files_with_counts(self):
            return []

    class Indexing:
        supported_extensions = {".md"}

        def all_index_roots(self):
            return []

    app = make_tui_app()
    app.comp = SimpleNamespace(storage=Storage(), config=SimpleNamespace(indexing=Indexing()))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-index"))
        app.render_index("one-time")
        await pilot.pause()
        app.query_one("#one-time-index-path").focus()

        await pilot.press("f7")
        assert app.index_section == "roots"
        assert app.focused is app.query_one("#index-tabs", Tabs)
        await pilot.pause()

        await pilot.press("f8")
        assert app.index_section == "one-time"
        assert app.focused is app.query_one("#index-tabs", Tabs)


async def test_tui_f_keys_do_nothing_without_active_tabs() -> None:
    app = make_tui_app()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        app.query_one("#search-query").focus()

        await pilot.press("f8")

        assert app.index_section == "overview"
        assert app.query_one("#search-query", Input).value == ""


async def test_tui_f_keys_move_tabs_only_in_focused_panel() -> None:
    app = make_tui_app()

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-test"))
        app.render_test_page()
        await pilot.pause()

        app.query_one("#test-input-one").focus()
        await pilot.press("f8")
        assert app.query_one("#test-tabs", Tabs).active == "test-tab-two"
        assert app.focused is app.query_one("#test-tabs", Tabs)
        assert app.query_one("#test-detail-tabs", Tabs).active == "test-detail-tab-alpha"

        app.focus_panel(app.PANEL_IDS.index("detail"))
        app.query_one("#test-detail-tabs", Tabs).focus()
        await pilot.pause()
        await pilot.press("f8")
        assert app.query_one("#test-tabs", Tabs).active == "test-tab-two"
        assert app.focused is app.query_one("#test-detail-tabs", Tabs)
        assert app.query_one("#test-detail-tabs", Tabs).active == "test-detail-tab-beta"

        app.focus_panel(app.PANEL_IDS.index("menu"))
        await pilot.pause()
        await pilot.press("f8")
        assert app.query_one("#test-tabs", Tabs).active == "test-tab-two"
        assert app.query_one("#test-detail-tabs", Tabs).active == "test-detail-tab-beta"


async def test_tui_preserves_input_values_across_tab_renders() -> None:
    app = make_tui_app()

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        app.focus_nav_button(app.NAV_BUTTON_IDS.index("nav-test"))
        app.render_test_page()
        await pilot.pause()

        first = app.query_one("#test-input-one", Input)
        first.value = "abcde"
        first.focus()

        await pilot.press("f8")
        await pilot.pause()
        second_a = app.query_one("#test-input-two-a", Input)
        second_b = app.query_one("#test-input-two-b", Input)
        second_a.value = "two-a"
        second_b.value = "two-b"

        await pilot.press("f8")
        await pilot.pause()
        assert not app.query(Input)

        await pilot.press("f7")
        await pilot.pause()
        assert app.query_one("#test-input-two-a", Input).value == "two-a"
        assert app.query_one("#test-input-two-b", Input).value == "two-b"

        await pilot.press("f7")
        await pilot.pause()
        assert app.query_one("#test-input-one", Input).value == "abcde"


async def test_tui_input_pastes_from_os_clipboard(monkeypatch) -> None:
    monkeypatch.setattr("memtomem.tui.app.read_os_clipboard", lambda: "한글 검색\nignored")

    app = make_tui_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        query = app.query_one("#search-query")
        query.focus()

        await pilot.press("ctrl+v")

        assert query.value == "한글 검색"


async def test_tui_input_copies_and_cuts_to_os_clipboard(monkeypatch) -> None:
    copied = []
    monkeypatch.setattr(
        "memtomem.tui.app.write_os_clipboard", lambda text: copied.append(text) or True
    )

    app = make_tui_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        query = app.query_one("#search-query")
        query.value = "abcdef"
        query.focus()
        await pilot.pause()
        query.selection = Selection(1, 4)

        await pilot.press("ctrl+c")
        await pilot.press("ctrl+x")

        assert copied == ["bcd", "bcd"]
        assert query.value == "aef"


async def test_tui_clipboard_keys_do_nothing_without_input_focus(monkeypatch) -> None:
    reads = []
    writes = []
    monkeypatch.setattr(
        "memtomem.tui.app.read_os_clipboard", lambda: reads.append(True) or "ignored"
    )
    monkeypatch.setattr(
        "memtomem.tui.app.write_os_clipboard", lambda text: writes.append(text) or True
    )

    app = make_tui_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        query = app.query_one("#search-query")
        query.value = "unchanged"
        app.query_one("#run-search", Button).focus()

        await pilot.press("ctrl+v")
        await pilot.press("ctrl+c")
        await pilot.press("ctrl+x")

        assert query.value == "unchanged"
        assert reads == []
        assert writes == []


async def test_tui_help_lists_clipboard_keys() -> None:
    app = make_tui_app()

    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()

        body = app.screen.query_one("#keybindings-body", Static).content
        assert "Clipboard" in body
        assert "Ctrl+C" in body
        assert "Ctrl+V" in body
        assert "Shift+Insert" in body
        assert "F7" in body
        assert "F8" in body
        assert "Ctrl+R" in body
        assert "Ctrl+Q" in body
        assert body.index("F6") < body.index("Alt+M")
