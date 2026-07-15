"""Generate the TUI rebuild's audited CLI parity inventory.

This development tool may inspect Click metadata. Production TUI modules must
never import ``memtomem.cli``; that boundary is enforced separately in tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import click


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "tui" / "parity-manifest.json"
BASELINE_PATH = REPO_ROOT / "docs" / "tui" / "cli-baseline.json"
CLI_ROOT = REPO_ROOT / "packages" / "memtomem" / "src" / "memtomem" / "cli"
PACKAGE_PYPROJECT = REPO_ROOT / "packages" / "memtomem" / "pyproject.toml"

MANUAL_FIELDS = (
    "validation",
    "preview_and_confirmation",
    "core_dependencies",
    "outputs",
    "errors_and_exit_meaning",
    "mutations_and_side_effects",
    "partial_failure",
    "cancellation",
    "tui_destination",
    "tests",
    "disposition",
    "decision_notes",
)

EXTRA_SURFACES = (
    {
        "id": "script:memtomem-server",
        "surface_kind": "console-script",
        "path": "memtomem-server",
        "entrypoint": "memtomem.server:main",
        "user_executable": True,
    },
    {
        "id": "script:memtomem-web",
        "surface_kind": "console-script",
        "path": "memtomem-web",
        "entrypoint": "memtomem.web.app:main",
        "user_executable": True,
    },
    {
        "id": "repl:ask",
        "surface_kind": "shell-repl",
        "path": "shell:ask",
        "user_executable": True,
    },
    {
        "id": "repl:aliases",
        "surface_kind": "shell-repl",
        "path": "shell:aliases",
        "user_executable": True,
    },
    {
        "id": "repl:implicit-search",
        "surface_kind": "shell-repl",
        "path": "shell:implicit-search",
        "user_executable": True,
    },
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return repr(value)


def _parameter(param: click.Parameter) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": param.name,
        "parameter_kind": "argument" if isinstance(param, click.Argument) else "option",
        "required": param.required,
        "default": _json_value(param.default),
        "type": param.type.name,
        "nargs": param.nargs,
        "multiple": param.multiple,
    }
    if isinstance(param, click.Option):
        row.update(
            {
                "opts": [*param.opts, *param.secondary_opts],
                "hidden": param.hidden,
                "is_flag": param.is_flag,
                "flag_value": _json_value(param.flag_value),
                "prompt": _json_value(param.prompt),
            }
        )
    return row


def _manual_defaults() -> dict[str, Any]:
    return {
        "validation": "unreviewed",
        "preview_and_confirmation": "unreviewed",
        "core_dependencies": [],
        "outputs": "unreviewed",
        "errors_and_exit_meaning": "unreviewed",
        "mutations_and_side_effects": "unreviewed",
        "partial_failure": "unreviewed",
        "cancellation": "unreviewed",
        "tui_destination": None,
        "tests": [],
        "disposition": None,
        "decision_notes": [],
    }


def _merge_manual(row: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    merged = {**row, **_manual_defaults()}
    if previous:
        for field in MANUAL_FIELDS:
            if field in previous:
                merged[field] = previous[field]
    return merged


def _click_rows(previous: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    # This import is intentionally local: only the audit tool may inspect CLI metadata.
    from memtomem.cli import cli

    rows: list[dict[str, Any]] = []

    def visit(command: click.Command, parents: tuple[str, ...]) -> None:
        path_parts = (*parents, command.name or "cli")
        path = " ".join(path_parts)
        is_group = isinstance(command, click.Group)
        invoke_without_command = bool(getattr(command, "invoke_without_command", False))
        row = {
            "id": f"click:{path}",
            "surface_kind": "click",
            "path": path,
            "command_kind": "group" if is_group else "command",
            "user_executable": not is_group or invoke_without_command,
            "hidden": command.hidden,
            "invoke_without_command": invoke_without_command,
            "help": command.help or "",
            "inputs": [_parameter(param) for param in command.params],
        }
        rows.append(_merge_manual(row, previous.get(row["id"])))
        if is_group:
            context = click.Context(command)
            for name in command.list_commands(context):
                child = command.get_command(context, name)
                if child is None:
                    raise RuntimeError(f"Click listed {path} {name!r} but did not resolve it")
                visit(child, path_parts)

    root_context = click.Context(cli)
    for name in cli.list_commands(root_context):
        child = cli.get_command(root_context, name)
        if child is None:
            raise RuntimeError(f"Click listed root command {name!r} but did not resolve it")
        visit(child, ("cli",))
    return rows


def load_manifest() -> dict[str, Any] | None:
    if not MANIFEST_PATH.exists():
        return None
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def build_manifest(existing: dict[str, Any] | None = None) -> dict[str, Any]:
    previous_rows = {row["id"]: row for row in (existing or {}).get("surfaces", []) if "id" in row}
    click_rows = _click_rows(previous_rows)
    extra_rows = [_merge_manual(dict(row), previous_rows.get(row["id"])) for row in EXTRA_SURFACES]
    groups = sum(row["command_kind"] == "group" for row in click_rows)
    leaves = sum(row["command_kind"] == "command" for row in click_rows)
    top_level = sum(row["path"].count(" ") == 1 for row in click_rows)
    click_executable = sum(row["user_executable"] for row in click_rows)
    return {
        "schema_version": 1,
        "authoritative_plan": (
            "packages/memtomem/src/memtomem/tui/AGENTS.md#authoritative-full-rebuild-plan-2026-07-15"
        ),
        "allowed_dispositions": [
            "native",
            "managed-external",
            "deferred",
            "not-applicable",
        ],
        "counts": {
            "top_level_click_commands": top_level,
            "click_command_paths": len(click_rows),
            "click_groups": groups,
            "click_leaf_commands": leaves,
            "click_user_executable_paths": click_executable,
            "additional_surfaces": len(extra_rows),
        },
        "surfaces": [*click_rows, *extra_rows],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_cli_baseline() -> dict[str, Any]:
    files = {
        path.relative_to(REPO_ROOT).as_posix(): _sha256(path)
        for path in sorted(CLI_ROOT.glob("*.py"))
    }
    scripts: dict[str, str] = {}
    in_scripts = False
    for raw_line in PACKAGE_PYPROJECT.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and line.startswith("["):
            break
        if in_scripts and line and not line.startswith("#"):
            name, value = line.split("=", 1)
            scripts[name.strip()] = value.strip().strip('"')
    return {"schema_version": 1, "cli_files_sha256": files, "project_scripts": scripts}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the manifest drifted")
    parser.add_argument(
        "--accept-cli-baseline",
        action="store_true",
        help="replace the frozen CLI hash/script baseline after an approved CLI change",
    )
    args = parser.parse_args()

    existing = load_manifest()
    manifest = build_manifest(existing)
    if args.check:
        if existing != manifest:
            raise SystemExit("TUI parity manifest drifted; regenerate it after auditing changes")
        if not BASELINE_PATH.exists():
            raise SystemExit("TUI CLI baseline is missing")
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        if baseline != build_cli_baseline():
            raise SystemExit(
                "CLI files or project script declarations changed from the TUI baseline"
            )
        return

    _write_json(MANIFEST_PATH, manifest)
    if args.accept_cli_baseline or not BASELINE_PATH.exists():
        _write_json(BASELINE_PATH, build_cli_baseline())


if __name__ == "__main__":
    main()
