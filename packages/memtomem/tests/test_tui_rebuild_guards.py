"""Architecture and inventory guards for the independent TUI rebuild."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[3]
TUI_ROOT = REPO_ROOT / "packages" / "memtomem" / "src" / "memtomem" / "tui"
MANIFEST_PATH = REPO_ROOT / "docs" / "tui" / "parity-manifest.json"
BASELINE_PATH = REPO_ROOT / "docs" / "tui" / "cli-baseline.json"
GENERATOR_PATH = REPO_ROOT / "tools" / "tui_parity_manifest.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tui_parity_manifest", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _import_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_tui_has_no_python_import_of_cli_modules() -> None:
    offenders: list[str] = []
    for path in sorted(TUI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            name == "memtomem.cli" or name.startswith("memtomem.cli.")
            for name in _import_names(tree)
        ):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == [], f"TUI production modules import memtomem.cli: {offenders}"


def test_parity_manifest_matches_current_click_tree() -> None:
    generator = _load_generator()
    existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert generator.build_manifest(existing) == existing


def test_parity_manifest_preserves_audited_counts_and_hidden_surfaces() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["counts"] == {
        "top_level_click_commands": 29,
        "click_command_paths": 87,
        "click_groups": 18,
        "click_leaf_commands": 69,
        "click_user_executable_paths": 70,
        "additional_surfaces": 5,
    }
    rows = {row["id"]: row for row in manifest["surfaces"]}
    assert rows["click:cli agent debug-resolve"]["hidden"] is True
    web_inputs = {item["name"]: item for item in rows["click:cli web"]["inputs"]}
    assert web_inputs["internal_foreground"]["hidden"] is True
    assert web_inputs["internal_foreground"]["opts"] == ["--_internal-foreground"]
    assert {
        "script:memtomem-server",
        "script:memtomem-web",
        "repl:ask",
        "repl:aliases",
        "repl:implicit-search",
    } <= rows.keys()


def test_cli_files_and_script_entries_match_frozen_rebuild_baseline() -> None:
    generator = _load_generator()
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert generator.build_cli_baseline() == baseline
    assert baseline["project_scripts"]["memtomem"] == "memtomem.cli:cli"
    assert baseline["project_scripts"]["mm"] == "memtomem.cli:cli"
