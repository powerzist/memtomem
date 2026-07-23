"""Phase 1 compatibility guards for replacing the old Textual composition."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from memtomem.cli import cli
from memtomem.config import IndexingConfig, Mem2MemConfig
from memtomem.tui import clipboard
from memtomem.tui import runtime
from memtomem.tui import terminal as tui_terminal
from memtomem.tui.app import MemtomemTuiApp, run, run_input_diagnostics
from memtomem.tui.runtime import ReadinessState, resolve_tui_paths
from memtomem.tui.terminal import choose_border_style, detect_terminal_profile


REPO_ROOT = Path(__file__).resolve().parents[3]
TUI_ROOT = REPO_ROOT / "packages" / "memtomem" / "src" / "memtomem" / "tui"


def test_tui_remains_visible_in_top_level_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.output


def test_tui_help_does_not_require_textual_runtime() -> None:
    result = CliRunner().invoke(cli, ["tui", "--help"])

    assert result.exit_code == 0
    assert "terminal UI" in result.output
    assert "--border" in result.output
    assert "--dev" in result.output
    assert "--diagnose-terminal" in result.output
    assert "--diagnose-input" in result.output
    assert "--mouse / --no-mouse" in result.output


def test_tui_missing_textual_keeps_install_hint(monkeypatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)

    result = CliRunner().invoke(cli, ["tui"])

    assert result.exit_code == 1
    assert "requires the [tui] extra" in result.output
    assert "memtomem[tui]" in result.output


def test_tui_terminal_diagnostics_remain_textual_independent(monkeypatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)

    result = CliRunner().invoke(cli, ["tui", "--diagnose-terminal"])

    assert result.exit_code == 0
    assert "memtomem TUI Terminal Diagnostics" in result.output
    assert "Rendering probes" in result.output
    assert "ASCII fallback" in result.output


def test_tui_launch_forwards_border_and_mouse_options(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr(
        "memtomem.tui.terminal.detect_terminal_profile",
        lambda *args, **kwargs: "windows-terminal",
    )
    monkeypatch.setattr("memtomem.tui.app.run", lambda **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(cli, ["tui", "--border", "ascii", "--no-mouse"])

    assert result.exit_code == 0
    assert calls == [
        {"border_style": "ascii", "mouse": False, "terminal_profile": "windows-terminal"}
    ]


def test_tui_dev_launch_forwards_contained_project_paths(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='memtomem'\n", encoding="utf-8")
    (tmp_path / "packages" / "memtomem").mkdir(parents=True)
    calls: list[dict[str, object]] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr(
        "memtomem.tui.terminal.detect_terminal_profile",
        lambda *args, **kwargs: "windows-terminal",
    )
    monkeypatch.setattr("memtomem.tui.app.run", lambda **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(cli, ["tui", "--dev"])

    assert result.exit_code == 0
    paths = calls[0]["paths"]
    assert paths.is_dev
    assert paths.state_root == tmp_path / ".dev" / ".memtomem"
    assert paths.config_path == paths.state_root / "config.json"
    assert paths.database_path == paths.state_root / "memtomem.db"
    assert paths.memories_path == paths.state_root / "memories"


def test_tui_dev_launch_still_requires_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())

    result = CliRunner().invoke(cli, ["tui", "--dev"])

    assert result.exit_code == 2
    assert "must be run from the memtomem project root" in result.output


def test_tui_input_diagnostics_still_uses_textual_launcher(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr("memtomem.tui.terminal.detect_terminal_profile", lambda: "windows-terminal")
    monkeypatch.setattr(
        "memtomem.tui.app.run_input_diagnostics",
        lambda **kwargs: calls.append(kwargs),
    )

    result = CliRunner().invoke(
        cli,
        ["tui", "--diagnose-input", "--border", "solid", "--no-mouse"],
    )

    assert result.exit_code == 0
    assert calls == [
        {"border_style": "solid", "mouse": False, "terminal_profile": "windows-terminal"}
    ]


def test_launcher_public_signatures_remain_compatible() -> None:
    run_parameters = inspect.signature(run).parameters
    diagnostics_parameters = inspect.signature(run_input_diagnostics).parameters

    assert tuple(run_parameters) == ("border_style", "mouse", "terminal_profile", "paths")
    assert tuple(diagnostics_parameters) == ("border_style", "mouse", "terminal_profile")
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in run_parameters.values()
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in diagnostics_parameters.values()
    )


def test_terminal_profile_and_border_contract() -> None:
    assert detect_terminal_profile({}, os_name="nt") == "windows-conhost"
    assert detect_terminal_profile({"WT_SESSION": "1"}, os_name="nt") == "windows-terminal"
    assert choose_border_style("auto", {}, os_name="nt") == "ascii"
    assert choose_border_style("auto", {"WT_SESSION": "1"}, os_name="nt") == "solid"
    assert choose_border_style("solid", {}, os_name="nt") == "solid"
    assert choose_border_style("ascii", {"WT_SESSION": "1"}, os_name="nt") == "ascii"


def test_windows_console_viewport_tolerates_missing_original_stdout(monkeypatch) -> None:
    monkeypatch.setattr(tui_terminal.os, "name", "nt")
    monkeypatch.setattr(tui_terminal.sys, "__stdout__", None)

    assert tui_terminal.windows_console_viewport_size() is None


def test_dev_paths_share_one_contained_state_root(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "packages" / "memtomem").mkdir(parents=True)

    paths = resolve_tui_paths(dev=True, cwd=tmp_path)

    assert paths.state_root == tmp_path.resolve() / ".dev" / ".memtomem"
    for path in (
        paths.config_path,
        paths.config_d_path,
        paths.database_path,
        paths.memories_path,
        paths.fastembed_cache_path,
    ):
        assert path.resolve().is_relative_to(paths.state_root.resolve())


def test_dev_config_replaces_only_the_isolated_user_tier(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "packages" / "memtomem").mkdir(parents=True)
    paths = resolve_tui_paths(dev=True, cwd=tmp_path)

    config = runtime.load_tui_config(paths)

    assert config.indexing.memory_dirs == [paths.memories_path]
    assert config.indexing.project_memory_dirs == []


def test_dev_config_rejects_index_roots_outside_the_isolated_state_tree(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "packages" / "memtomem").mkdir(parents=True)
    paths = resolve_tui_paths(dev=True, cwd=tmp_path)
    paths.config_path.parent.mkdir(parents=True)
    paths.config_path.write_text(
        '{"indexing": {"memory_dirs": ["C:/outside/memories"]}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"indexing\.all_index_roots\(\)\[0\].*must stay under"):
        runtime.load_tui_config(paths)


async def test_readiness_fans_out_across_user_and_project_roots(tmp_path: Path) -> None:
    class EmptyStorage:
        async def get_stats(self) -> dict[str, int]:
            return {"total_chunks": 0, "total_sources": 0}

    user_root = tmp_path / "user-memories"
    project_root = tmp_path / "project" / ".memtomem" / "memories"
    user_root.mkdir()
    project_root.mkdir(parents=True)
    (project_root / "project-note.md").write_text("# Project memory\n", encoding="utf-8")
    config = Mem2MemConfig(
        indexing=IndexingConfig(
            memory_dirs=[user_root],
            project_memory_dirs=[project_root],
        )
    )
    components = SimpleNamespace(config=config, storage=EmptyStorage())

    readiness = await runtime.inspect_readiness(components)

    assert readiness.state is ReadinessState.INDEX_REQUIRED
    assert readiness.memory_dirs == (user_root, project_root)
    assert readiness.indexable_files == 1


def test_focus_and_keyboard_bindings_remain_exposed() -> None:
    bindings = {(binding.key, binding.action) for binding in MemtomemTuiApp.BINDINGS}

    assert {
        ("f2", "focus_menu"),
        ("f3", "focus_main"),
        ("f4", "focus_detail"),
        ("f6,alt+m", "toggle_mouse_mode"),
        ("f7", "tab_previous"),
        ("f8", "tab_next"),
        ("page_up", "page_up"),
        ("page_down", "page_down"),
        ("ctrl+q", "request_quit"),
        ("escape", "escape"),
    } <= bindings


def test_clipboard_helpers_keep_best_effort_public_contract() -> None:
    assert tuple(inspect.signature(clipboard.read_os_clipboard).parameters) == ()
    assert tuple(inspect.signature(clipboard.write_os_clipboard).parameters) == ("text",)
    assert clipboard._run_clipboard_command(None, []) is None
    assert clipboard._send_clipboard_command(None, [], "text") is False


def test_workers_receive_lazy_work_instead_of_eager_coroutines() -> None:
    """Prevent cancelled exclusive workers from leaking unawaited coroutines."""

    offenders: list[str] = []
    for path in sorted(TUI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "run_worker" or not node.args:
                continue
            work = node.args[0]
            if not isinstance(work, ast.Call):
                continue
            is_lazy_partial = isinstance(work.func, ast.Name) and work.func.id == "partial"
            if not is_lazy_partial:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}")

    assert offenders == [], f"run_worker received eager coroutine calls at {offenders}"
