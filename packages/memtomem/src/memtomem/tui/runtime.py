"""Runtime readiness checks for the Textual UI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from memtomem.config import Mem2MemConfig
    from memtomem.server.component_factory import Components


CONFIG_PATH = Path.home() / ".memtomem" / "config.json"


@dataclass(frozen=True)
class TuiPaths:
    """Persistent paths selected once for a TUI process."""

    mode: Literal["normal", "dev"]
    project_root: Path | None
    state_root: Path
    config_path: Path
    config_d_path: Path
    database_path: Path
    memories_path: Path

    @property
    def is_dev(self) -> bool:
        return self.mode == "dev"

    @property
    def fastembed_cache_path(self) -> Path:
        """Return the TUI-owned FastEmbed cache inside the selected state root."""

        return self.state_root / "cache" / "fastembed"


def resolve_tui_paths(*, dev: bool, cwd: Path | None = None) -> TuiPaths:
    """Resolve the single canonical state tree for this TUI process."""

    if dev:
        project_root = (cwd or Path.cwd()).resolve()
        if (
            not (project_root / "pyproject.toml").is_file()
            or not (project_root / "packages" / "memtomem").is_dir()
        ):
            raise ValueError("--dev must be run from the memtomem project root")
        state_root = project_root / ".dev" / ".memtomem"
        mode: Literal["normal", "dev"] = "dev"
    else:
        project_root = None
        state_root = Path.home() / ".memtomem"
        mode = "normal"
    return TuiPaths(
        mode=mode,
        project_root=project_root,
        state_root=state_root,
        config_path=state_root / "config.json",
        config_d_path=state_root / "config.d",
        database_path=state_root / "memtomem.db",
        memories_path=state_root / "memories",
    )


def _dev_default_config(paths: TuiPaths) -> Mem2MemConfig:
    from memtomem.config import IndexingConfig, Mem2MemConfig

    # Development mode intentionally replaces the user-tier root so it cannot
    # consult normal ~/.memtomem state. Construct that scope explicitly rather
    # than mutating the registry after validation.
    config = Mem2MemConfig(indexing=IndexingConfig(memory_dirs=[paths.memories_path]))
    config.storage.sqlite_path = paths.database_path
    return config


def load_tui_config(paths: TuiPaths) -> Mem2MemConfig:
    """Load config without allowing dev mode to consult normal state files."""

    from memtomem.config import Mem2MemConfig, load_config_d, load_config_overrides

    if not paths.is_dev:
        config = Mem2MemConfig()
        load_config_d(config, strict_read=True)
        load_config_overrides(config, strict_read=True)
        return config

    config = _dev_default_config(paths)
    load_config_d(
        config,
        config_d_path=paths.config_d_path,
        strict_read=True,
    )
    load_config_overrides(
        config,
        migrate=False,
        override_path=paths.config_path,
        strict_read=True,
    )
    _validate_dev_config_containment(paths, config)
    return config


def load_tui_config_read_only(paths: TuiPaths) -> Mem2MemConfig:
    """Load the selected TUI config without running persistence migrations.

    Home and Status use this loader before the mutable runtime exists.  Both
    normal and development modes receive their resolved paths explicitly so a
    diagnostic read cannot silently fall back to another state tree.
    """

    from memtomem.config import Mem2MemConfig, load_config_d, load_config_overrides

    config = _dev_default_config(paths) if paths.is_dev else Mem2MemConfig()
    load_config_d(
        config,
        quiet=True,
        config_d_path=paths.config_d_path,
        strict_read=True,
    )
    load_config_overrides(
        config,
        migrate=False,
        override_path=paths.config_path,
        strict_read=True,
    )
    _validate_dev_config_containment(paths, config)
    return config


def _validate_dev_config_containment(paths: TuiPaths, config: Mem2MemConfig) -> None:
    """Reject persisted dev paths that escape the isolated TUI state tree."""

    if not paths.is_dev:
        return
    state_root = paths.state_root.resolve()
    candidates = (
        ("storage.sqlite_path", Path(config.storage.sqlite_path)),
        *(
            (f"indexing.all_index_roots()[{index}]", Path(path))
            for index, path in enumerate(config.indexing.all_index_roots())
        ),
    )
    for field_name, candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if not resolved.is_relative_to(state_root):
            raise ValueError(f"development {field_name} must stay under {paths.state_root}")


def save_tui_config(paths: TuiPaths, config: Mem2MemConfig) -> None:
    """Persist TUI changes into the selected normal or development config."""

    from memtomem.config import load_config_d, save_config_overrides

    if not paths.is_dev:
        save_config_overrides(config)
        return
    _validate_dev_config_containment(paths, config)
    comparand = _dev_default_config(paths)
    load_config_d(comparand, quiet=True, config_d_path=paths.config_d_path)
    save_config_overrides(
        config,
        override_path=paths.config_path,
        comparand=comparand,
    )


def initialize_tui_config(paths: TuiPaths, *, state: object) -> None:
    """Persist a completed TUI-owned init state and its optional integrations."""
    import json
    import subprocess

    from memtomem.tui.init_flow import TuiInitState

    if not isinstance(state, TuiInitState):
        raise TypeError("state must be TuiInitState")
    resolved_memory_dir = Path(state.memory_dir).expanduser().resolve()
    resolved_memory_dir.mkdir(parents=True, exist_ok=True)

    config_data: dict[str, object] = {
        "embedding": {
            "provider": state.provider,
            "model": state.model,
            "dimension": state.dimension,
            "api_key": state.api_key,
        },
        "storage": {
            "backend": "sqlite",
            "sqlite_path": str(
                paths.database_path if paths.is_dev else Path(state.db_path).expanduser()
            ),
        },
        "indexing": {
            "memory_dirs": [str(resolved_memory_dir), *state.provider_dirs],
            "auto_discover": False,
        },
        "namespace": {
            "enable_auto_ns": state.enable_auto_ns,
            "default_namespace": state.default_ns,
        },
        "search": {
            "default_top_k": state.top_k,
            "tokenizer": state.tokenizer,
        },
        "decay": {"enabled": state.decay_enabled},
        "rerank": {
            "enabled": state.rerank_enabled,
            "provider": "fastembed",
            "model": state.rerank_model,
        },
    }
    paths.config_path.parent.mkdir(parents=True, exist_ok=True)
    paths.config_path.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    server_command = (
        ["uv", "run", "--directory", str(paths.project_root), "memtomem-server"]
        if paths.is_dev and paths.project_root
        else ["uvx", "--from", "memtomem", "memtomem-server"]
    )
    mcp_entry: dict[str, object] = {
        "command": server_command[0],
        "args": server_command[1:],
    }
    if state.mcp_choice == 1:
        try:
            subprocess.run(
                ["claude", "mcp", "add", "memtomem", "-s", "user", "--", *server_command],
                check=False,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            _write_tui_mcp_json(Path.cwd() / ".mcp.json", mcp_entry)
    elif state.mcp_choice == 2:
        _write_tui_mcp_json(Path.cwd() / ".mcp.json", mcp_entry)
    elif state.mcp_choice == 4:
        _write_tui_mcp_json(Path.home() / ".kimi" / "mcp.json", mcp_entry)

    if state.settings_hooks and (Path.home() / ".claude").is_dir():
        from memtomem.context.settings import CANONICAL_SETTINGS_FILE, generate_all_settings

        canonical = Path.cwd() / CANONICAL_SETTINGS_FILE
        canonical.parent.mkdir(parents=True, exist_ok=True)
        if not canonical.exists():
            canonical.write_text('{"hooks": {}}\n', encoding="utf-8")
        generate_all_settings(Path.cwd(), scope="user")


def _write_tui_mcp_json(path: Path, server_entry: dict[str, object]) -> None:
    """Write or merge the TUI wizard's memtomem MCP entry."""
    import json

    data: dict[str, object] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    servers = data.setdefault("mcpServers", {})
    if isinstance(servers, dict):
        servers["memtomem"] = server_entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@asynccontextmanager
async def tui_components(paths: TuiPaths) -> AsyncIterator[Components]:
    """Create components without crossing the selected TUI state boundary."""

    from memtomem.server.component_factory import close_components, create_components

    comp = await create_components(load_tui_config(paths), load_persisted_config=False)
    try:
        yield comp
    finally:
        await close_components(comp)


class ReadinessState(str, Enum):
    """High-level states that decide the TUI's first screen."""

    SETUP_REQUIRED = "setup_required"
    INDEX_TARGETS_REQUIRED = "index_targets_required"
    INDEX_REQUIRED = "index_required"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class Readiness:
    state: ReadinessState
    message: str
    total_chunks: int = 0
    total_sources: int = 0
    memory_dirs: tuple[Path, ...] = ()
    indexable_files: int = 0
    error: str | None = None


def config_exists(config_path: Path = CONFIG_PATH) -> bool:
    """Return whether the persisted ``mm init`` config exists."""

    return config_path.exists()


def count_indexable_files(memory_dirs: tuple[Path, ...], extensions: set[str]) -> int:
    """Count configured indexable files with a bounded, best-effort walk.

    This is intentionally cheap enough for startup. The TUI only needs to
    distinguish "empty DB because there is nothing to index" from "empty DB
    while configured folders contain indexable material." Exact progress is
    shown later by the indexing screen.
    """

    total = 0
    for root in memory_dirs:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if not resolved.exists():
            continue
        if resolved.is_file():
            if resolved.suffix.lower() in extensions:
                total += 1
            continue
        try:
            for path in resolved.rglob("*"):
                if path.is_file() and path.suffix.lower() in extensions:
                    total += 1
        except OSError:
            continue
    return total


async def inspect_readiness(comp: Components) -> Readiness:
    """Inspect configured state and index coverage for startup routing."""

    try:
        memory_dirs = tuple(
            Path(path).expanduser() for path in comp.config.indexing.all_index_roots()
        )
        if not memory_dirs:
            return Readiness(
                state=ReadinessState.INDEX_TARGETS_REQUIRED,
                message="No memory directories are configured. Add a memory directory first.",
            )

        stats = await comp.storage.get_stats()
        total_chunks = int(stats.get("total_chunks", 0))
        total_sources = int(stats.get("total_sources", 0))
        if total_chunks > 0 and total_sources > 0:
            return Readiness(
                state=ReadinessState.READY,
                message="memtomem is ready.",
                total_chunks=total_chunks,
                total_sources=total_sources,
                memory_dirs=memory_dirs,
            )

        extensions = {ext.lower() for ext in comp.config.indexing.supported_extensions}
        indexable = count_indexable_files(memory_dirs, extensions)
        if indexable > 0:
            return Readiness(
                state=ReadinessState.INDEX_REQUIRED,
                message="Indexable files were found, but the memory index is empty.",
                total_chunks=total_chunks,
                total_sources=total_sources,
                memory_dirs=memory_dirs,
                indexable_files=indexable,
            )

        return Readiness(
            state=ReadinessState.READY,
            message="memtomem is configured, but no indexable files were found.",
            total_chunks=total_chunks,
            total_sources=total_sources,
            memory_dirs=memory_dirs,
            indexable_files=0,
        )
    except Exception as exc:
        return Readiness(
            state=ReadinessState.ERROR,
            message="Could not inspect memtomem runtime state.",
            error=str(exc),
        )
