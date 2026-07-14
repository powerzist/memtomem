"""TUI-owned implementation model for the ``mm init`` experience.

The CLI remains the stable primary interface. This module intentionally does
not call or refactor the Click wizard; it mirrors that user-facing contract for
the Textual implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

PresetName = Literal["minimal", "english", "korean"]


@dataclass(frozen=True)
class TuiInitPreset:
    label: str
    description: str
    provider: str
    model: str
    dimension: int
    rerank_enabled: bool
    rerank_model: str
    tokenizer: str
    auto_ns: bool
    autodetect_providers: bool


PRESETS: dict[PresetName, TuiInitPreset] = {
    "minimal": TuiInitPreset(
        "Minimal",
        "BM25 keyword search - no downloads, no dependencies",
        "none",
        "",
        0,
        False,
        "Xenova/ms-marco-MiniLM-L-6-v2",
        "unicode61",
        False,
        False,
    ),
    "english": TuiInitPreset(
        "English (Recommended)",
        "ONNX bge-small-en-v1.5 + English rerank + auto-discover providers",
        "onnx",
        "bge-small-en-v1.5",
        384,
        True,
        "Xenova/ms-marco-MiniLM-L-6-v2",
        "unicode61",
        True,
        True,
    ),
    "korean": TuiInitPreset(
        "Korean-optimized",
        "ONNX bge-m3 + Korean tokenizer + multilingual rerank",
        "onnx",
        "bge-m3",
        1024,
        True,
        "jinaai/jina-reranker-v2-base-multilingual",
        "kiwipiepy",
        True,
        True,
    ),
}

PRESET_STEPS = (
    "Setup style",
    "Memory Directory",
    "Provider Memory Folders",
    "Connect to AI Editor",
)
ADVANCED_STEPS = (
    "Embedding Provider",
    "Reranker (optional)",
    "Memory Directory",
    "Provider Memory Folders",
    "Storage",
    "Namespace",
    "Search",
    "Language",
    "Claude Code Hooks",
    "Connect to AI Editor",
)


@dataclass
class TuiInitState:
    mode: Literal["preset", "advanced"] = "preset"
    preset_name: PresetName = "english"
    provider: str = "none"
    model: str = ""
    dimension: int = 0
    api_key: str = ""
    rerank_enabled: bool = False
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    memory_dir: str = "~/memories"
    provider_categories: set[str] = field(default_factory=set)
    provider_dirs: list[str] = field(default_factory=list)
    db_path: str = "~/.memtomem/memtomem.db"
    enable_auto_ns: bool = False
    default_ns: str = "default"
    top_k: int = 10
    decay_enabled: bool = False
    tokenizer: str = "unicode61"
    settings_hooks: bool = False
    mcp_choice: int = 1

    def apply_preset(self) -> None:
        preset = PRESETS[self.preset_name]
        self.provider = preset.provider
        self.model = preset.model
        self.dimension = preset.dimension
        self.rerank_enabled = preset.rerank_enabled
        self.rerank_model = preset.rerank_model
        self.tokenizer = preset.tokenizer
        self.enable_auto_ns = preset.auto_ns
        self.default_ns = "default"
        self.top_k = 10
        self.decay_enabled = False

    @property
    def steps(self) -> tuple[str, ...]:
        return PRESET_STEPS if self.mode == "preset" else ADVANCED_STEPS


def detect_provider_dirs() -> dict[str, list[Path]]:
    """Detect the provider folders offered by the TUI wizard."""
    home = Path.home()
    grouped: dict[str, list[Path]] = {
        "claude-memory": [],
        "claude-plans": [],
        "codex": [],
    }
    projects = home / ".claude" / "projects"
    if projects.is_dir():
        grouped["claude-memory"] = sorted(
            path for path in projects.glob("*/memory") if path.is_dir()
        )
    plans = home / ".claude" / "plans"
    if plans.is_dir():
        grouped["claude-plans"] = [plans]
    codex = home / ".codex" / "memories"
    if codex.is_dir():
        grouped["codex"] = [codex]
    return grouped
