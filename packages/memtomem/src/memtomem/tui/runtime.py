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
    from memtomem.config import Mem2MemConfig

    config = Mem2MemConfig()
    config.storage.sqlite_path = paths.database_path
    config.indexing.memory_dirs = [paths.memories_path]
    return config


def load_tui_config(paths: TuiPaths) -> Mem2MemConfig:
    """Load config without allowing dev mode to consult normal state files."""

    from memtomem.config import Mem2MemConfig, load_config_d, load_config_overrides

    if not paths.is_dev:
        config = Mem2MemConfig()
        load_config_d(config)
        load_config_overrides(config)
        return config

    config = _dev_default_config(paths)
    load_config_d(config, config_d_path=paths.config_d_path)
    load_config_overrides(config, migrate=False, override_path=paths.config_path)
    database_path = Path(config.storage.sqlite_path).expanduser().resolve()
    if not database_path.is_relative_to(paths.state_root.resolve()):
        raise ValueError(f"development storage.sqlite_path must stay under {paths.state_root}")
    return config


def save_tui_config(paths: TuiPaths, config: Mem2MemConfig) -> None:
    """Persist TUI changes into the selected normal or development config."""

    from memtomem.config import load_config_d, save_config_overrides

    if not paths.is_dev:
        save_config_overrides(config)
        return
    comparand = _dev_default_config(paths)
    load_config_d(comparand, quiet=True, config_d_path=paths.config_d_path)
    save_config_overrides(
        config,
        override_path=paths.config_path,
        comparand=comparand,
    )


@asynccontextmanager
async def tui_components(paths: TuiPaths) -> AsyncIterator[Components]:
    """Create components without crossing the selected TUI state boundary."""

    if not paths.is_dev:
        from memtomem.cli._bootstrap import cli_components

        async with cli_components() as comp:
            yield comp
        return

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
        memory_dirs = tuple(Path(p).expanduser() for p in comp.config.indexing.memory_dirs)
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
