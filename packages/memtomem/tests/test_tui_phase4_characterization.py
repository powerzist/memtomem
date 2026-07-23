"""Phase 4 parity characterization for native Home/Status and Search."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "docs" / "tui" / "parity-manifest.json"


def _rows() -> dict[str, dict[str, object]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in manifest["surfaces"]}


def test_search_inventory_keeps_the_cli_input_contract() -> None:
    search = _rows()["click:cli search"]
    inputs = {item["name"]: item for item in search["inputs"]}

    assert tuple(inputs) == (
        "query",
        "top_k",
        "source_filter",
        "tag_filter",
        "namespace",
        "scope",
        "as_of",
        "fmt",
    )
    assert inputs["query"]["required"] is True
    assert inputs["top_k"]["default"] == 10
    assert inputs["top_k"]["type"] == "integer"
    assert inputs["fmt"]["default"] == "table"
    assert inputs["fmt"]["type"] == "choice"


def test_phase4_closes_only_native_search_and_status_rows() -> None:
    rows = _rows()
    search = rows["click:cli search"]
    status = rows["click:cli status"]
    implicit_search = rows["repl:implicit-search"]

    assert search["disposition"] == "native"
    assert search["tui_destination"] == (
        "Memories / Search in Main; selected result in contextual Details (F4)"
    )
    assert "non-cancellable" in search["cancellation"]
    assert "Phase 12" in search["cancellation"]
    assert "--format" in search["decision_notes"][1]
    assert "search.default_top_k" in search["validation"]
    assert any("2026-07-19" in note for note in search["decision_notes"])
    assert set(search["tests"]) >= {
        "test_tui_search_service.py",
        "test_tui_phase4_widgets.py",
        "test_tui_phase4_interactions.py",
    }

    assert status["disposition"] == "native"
    assert status["preview_and_confirmation"].startswith("Not applicable")
    assert "None" in status["mutations_and_side_effects"]
    assert "mode=ro" in status["core_dependencies"][2]

    assert implicit_search["disposition"] is None
    assert implicit_search["validation"] == "unreviewed"
    assert implicit_search["tui_destination"] is None
