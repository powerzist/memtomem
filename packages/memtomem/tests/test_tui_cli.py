"""Tests for the ``mm tui`` entry point and command catalog."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from click.testing import CliRunner
from textual.widgets import Button, ListItem, ListView, Static
from textual.widgets._input import Selection

from memtomem.cli import cli
from memtomem.models import Chunk, ChunkMetadata, SearchResult
from memtomem.tui import clipboard as tui_clipboard
from memtomem.tui.app import (
    ConhostWarningScreen,
    InputDiagnosticsApp,
    KeybindingsScreen,
    MemtomemTuiApp,
)
from memtomem.tui import runtime
from memtomem.tui.catalog import COMMAND_CATALOG
from memtomem.tui.runtime import ReadinessState
from memtomem.tui.terminal import choose_border_style, detect_terminal_profile


def make_tui_app(*, border_style: str = "solid") -> MemtomemTuiApp:
    return MemtomemTuiApp(
        border_style=border_style,
        startup_refresh=False,
        terminal_profile="windows-terminal",
        mouse_enabled=True,
    )


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
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None if name == "textual" else None)

    result = CliRunner().invoke(cli, ["tui"])

    assert result.exit_code == 1
    assert "requires the [tui] extra" in result.output
    assert "memtomem[tui]" in result.output


def test_tui_diagnose_terminal_does_not_require_textual(monkeypatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None if name == "textual" else None)

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

        warnings = [widget.content for widget in app.query("#main-body .warning").results(Static)]
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
        await pilot.press("alt+m")
        assert app.query_one("#mouse-status", Static).content == "Mouse:OS"
        await pilot.press("alt+m")
        assert app.query_one("#mouse-status", Static).content == "Mouse:TUI"

    assert calls == [False, True]


async def test_tui_input_diagnostics_warns_about_conhost_ime_limitations() -> None:
    app = InputDiagnosticsApp(terminal_profile="windows-conhost")

    async with app.run_test() as pilot:
        await pilot.pause()

        warnings = [widget.content for widget in app.query("#diagnostics .warning").results(Static)]
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

        await pilot.press("right")
        assert getattr(app.focused, "id", None) == "main-one"

        await pilot.press("down")
        assert getattr(app.focused, "id", None) == "main-two"

        await pilot.press("up")
        assert getattr(app.focused, "id", None) == "main-one"

        app.render_catalog()
        await pilot.pause()
        app.focus_panel(0)
        await pilot.press("right")
        assert isinstance(app.focused, ListView)

        app.focused.index = 0
        await pilot.press("down")
        assert app.focused.index == 1


async def test_tui_ascii_border_class_is_applied() -> None:
    app = make_tui_app(border_style="ascii")

    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.query_one("#nav").has_class("ascii-border")
        assert app.query_one("#main").has_class("ascii-border")
        assert app.query_one("#detail").has_class("ascii-border")


async def test_tui_help_uses_selected_border_style() -> None:
    app = make_tui_app(border_style="ascii")

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("?")

        assert isinstance(app.screen, KeybindingsScreen)
        assert app.screen.query_one("#keybindings-dialog").has_class("ascii-border")


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
        await pilot.press("pagedown")
        assert body.scroll_y > 0

        await pilot.press("pageup")
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
    monkeypatch.setattr("memtomem.tui.app.write_os_clipboard", lambda text: copied.append(text) or True)

    app = make_tui_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.render_search()
        await pilot.pause()
        query = app.query_one("#search-query")
        query.value = "abcdef"
        query.selection = Selection(1, 4)
        query.focus()

        await pilot.press("ctrl+c")
        await pilot.press("ctrl+x")

        assert copied == ["bcd", "bcd"]
        assert query.value == "aef"


async def test_tui_clipboard_keys_do_nothing_without_input_focus(monkeypatch) -> None:
    reads = []
    writes = []
    monkeypatch.setattr("memtomem.tui.app.read_os_clipboard", lambda: reads.append(True) or "ignored")
    monkeypatch.setattr("memtomem.tui.app.write_os_clipboard", lambda text: writes.append(text) or True)

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
