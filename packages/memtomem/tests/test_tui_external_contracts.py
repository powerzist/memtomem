"""Phase 1 compatibility guards for replacing the old Textual composition."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from memtomem.tui import clipboard
from memtomem.tui.app import MemtomemTuiApp, run, run_input_diagnostics
from memtomem.tui.runtime import resolve_tui_paths
from memtomem.tui.terminal import choose_border_style, detect_terminal_profile


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_PATH = REPO_ROOT / "packages" / "memtomem" / "src" / "memtomem" / "tui" / "app.py"


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
    ):
        assert path.resolve().is_relative_to(paths.state_root.resolve())


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

    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    offenders: list[int] = []
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
            offenders.append(node.lineno)

    assert offenders == [], f"run_worker received eager coroutine calls at lines {offenders}"
