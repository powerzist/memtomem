"""Runtime readiness checks for the Textual UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memtomem.server.component_factory import Components


CONFIG_PATH = Path.home() / ".memtomem" / "config.json"


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
