"""Strictly read-only Home and Status diagnostics.

This adapter intentionally does not acquire a :class:`RuntimeManager` lease.
Configuration is loaded with migrations disabled and SQLite is opened through
its read-only URI mode, keeping the Home surface observational under Gate 9.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from memtomem.tui.application.contracts import UserSafeWarning
from memtomem.tui.runtime import TuiPaths, load_tui_config_read_only

if TYPE_CHECKING:
    from memtomem.config import Mem2MemConfig


class SetupState(str, Enum):
    """Whether the normal setup artifact can be inspected."""

    REQUIRED = "required"
    CONFIGURED = "configured"
    ERROR = "error"


class DatabaseState(str, Enum):
    """Read-only accessibility of the configured SQLite database."""

    MISSING = "missing"
    READABLE = "readable"
    UNREADABLE = "unreadable"


class SchemaState(str, Enum):
    """Search-critical schema state observed without running migrations."""

    UNAVAILABLE = "unavailable"
    READY = "ready"
    MIGRATION_REQUIRED = "migration_required"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class SetupDiagnostic:
    state: SetupState
    config_path: Path
    memory_dirs: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class DatabaseDiagnostic:
    state: DatabaseState
    path: Path


@dataclass(frozen=True, slots=True)
class SchemaDiagnostic:
    state: SchemaState
    missing_tables: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()
    missing_indexes: tuple[str, ...] = ()
    pending_migrations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DenseCoverage:
    total: int
    with_dense: int

    def __post_init__(self) -> None:
        if self.total < 0 or self.with_dense < 0:
            raise ValueError("dense coverage counts must be non-negative")
        if self.with_dense > self.total:
            raise ValueError("dense coverage cannot exceed the chunk count")

    @property
    def missing(self) -> int:
        return self.total - self.with_dense

    @property
    def ratio(self) -> float | None:
        if self.total == 0:
            return None
        return self.with_dense / self.total


@dataclass(frozen=True, slots=True)
class EmbeddingDiagnostic:
    configured_dimension: int
    configured_provider: str
    configured_model: str
    stored_dimension: int | None
    stored_provider: str | None
    stored_model: str | None
    dimension_mismatch: bool
    model_mismatch: bool

    @property
    def mismatch(self) -> bool:
        return self.dimension_mismatch or self.model_mismatch


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    setup: SetupDiagnostic
    database: DatabaseDiagnostic
    schema: SchemaDiagnostic
    storage_backend: str = ""
    default_top_k: int = 0
    rrf_k: int = 0
    tokenizer: str = ""
    scheduler_enabled: bool = False
    health_watchdog_enabled: bool = False
    chunks: int | None = None
    sources: int | None = None
    orphans: int | None = None
    dense_coverage: DenseCoverage | None = None
    embedding: EmbeddingDiagnostic | None = None
    warnings: tuple[UserSafeWarning, ...] = ()


_REQUIRED_TABLES = frozenset(
    {
        "_memtomem_meta",
        "access_log",
        "chunk_entities",
        "chunk_links",
        "chunk_relations",
        "chunks",
        "chunks_fts",
        "health_snapshots",
        "memory_policies",
        "namespace_metadata",
        "query_history",
        "schedules",
        "session_events",
        "sessions",
        "working_memory",
    }
)
_REQUIRED_INDEXES = frozenset(
    {
        "idx_access_log_chunk",
        "idx_access_log_created",
        "idx_chunk_links_namespace",
        "idx_chunk_links_source",
        "idx_chunks_access_count",
        "idx_chunks_created_at",
        "idx_chunks_hash",
        "idx_chunks_importance",
        "idx_chunks_namespace",
        "idx_chunks_project_root",
        "idx_chunks_scope",
        "idx_chunks_source",
        "idx_chunks_unique_content",
        "idx_entities_chunk",
        "idx_entities_type",
        "idx_entities_type_value",
        "idx_health_snap_name",
        "idx_query_history_created",
        "idx_relations_source",
        "idx_relations_target",
        "idx_schedules_enabled",
        "idx_session_events_session",
        "idx_sessions_agent",
        "idx_sessions_started",
        "idx_working_expires",
        "idx_working_session_created",
    }
)
_REQUIRED_CHUNK_COLUMNS = frozenset(
    {
        "access_count",
        "content",
        "created_at",
        "id",
        "importance_score",
        "last_accessed_at",
        "namespace",
        "project_root",
        "scope",
        "source_file",
        "tags",
        "updated_at",
        "use_count",
        "valid_from_unix",
        "valid_to_unix",
    }
)
_CHUNK_LINKS_BACKFILL_KEY = "chunk_links_backfill_v1"


class _SnapshotConfig(TypedDict):
    storage_backend: str
    default_top_k: int
    rrf_k: int
    tokenizer: str
    scheduler_enabled: bool
    health_watchdog_enabled: bool


class ReadOnlyDiagnosticsService:
    """Collect a structured snapshot without starting mutable components."""

    def __init__(self, paths: TuiPaths) -> None:
        self._paths = paths

    async def inspect(self) -> DiagnosticsSnapshot:
        return await asyncio.to_thread(_inspect_sync, self._paths)


async def inspect_read_only_diagnostics(paths: TuiPaths) -> DiagnosticsSnapshot:
    """Convenience entry point for a one-shot read-only diagnostic."""

    return await ReadOnlyDiagnosticsService(paths).inspect()


def _inspect_sync(paths: TuiPaths) -> DiagnosticsSnapshot:
    warnings: list[UserSafeWarning] = []
    try:
        config = load_tui_config_read_only(paths)
    except Exception:
        warning = UserSafeWarning(
            code="diagnostics.config_unreadable",
            message="Configuration could not be inspected safely.",
            recovery_action="Review the configuration files before starting Search.",
        )
        return DiagnosticsSnapshot(
            setup=SetupDiagnostic(SetupState.ERROR, paths.config_path),
            database=DatabaseDiagnostic(DatabaseState.UNREADABLE, paths.database_path),
            schema=SchemaDiagnostic(SchemaState.UNAVAILABLE),
            warnings=(warning,),
        )

    memory_dirs = tuple(Path(root).expanduser() for root in config.indexing.all_index_roots())
    setup_state = SetupState.CONFIGURED if paths.config_path.is_file() else SetupState.REQUIRED
    if setup_state is SetupState.REQUIRED:
        warnings.append(
            UserSafeWarning(
                code="diagnostics.setup_required",
                message="Setup has not been completed.",
                recovery_action="Complete setup before running Search.",
            )
        )
    setup = SetupDiagnostic(setup_state, paths.config_path, memory_dirs)
    database_path = Path(config.storage.sqlite_path).expanduser().resolve()
    embedding = _configured_embedding(config)
    snapshot_config = _snapshot_config(config)
    if config.scheduler.enabled and not config.health_watchdog.enabled:
        warnings.append(
            UserSafeWarning(
                code="diagnostics.scheduler_inactive",
                message="Schedules are enabled, but the health watchdog is disabled.",
                recovery_action="Enable the health watchdog before relying on schedules.",
            )
        )

    if not database_path.is_file():
        warnings.append(
            UserSafeWarning(
                code="diagnostics.database_missing",
                message="The search database does not exist.",
                recovery_action="Enter Search only when runtime initialization is acceptable.",
            )
        )
        return DiagnosticsSnapshot(
            setup=setup,
            database=DatabaseDiagnostic(DatabaseState.MISSING, database_path),
            schema=SchemaDiagnostic(SchemaState.UNAVAILABLE),
            embedding=embedding,
            **snapshot_config,
            warnings=tuple(warnings),
        )

    try:
        observed = _read_database(database_path, config)
    except (OSError, sqlite3.Error):
        warnings.append(
            UserSafeWarning(
                code="diagnostics.database_unreadable",
                message="The search database could not be inspected in read-only mode.",
                recovery_action="Check database access before starting Search.",
            )
        )
        return DiagnosticsSnapshot(
            setup=setup,
            database=DatabaseDiagnostic(DatabaseState.UNREADABLE, database_path),
            schema=SchemaDiagnostic(SchemaState.UNREADABLE),
            embedding=embedding,
            **snapshot_config,
            warnings=tuple(warnings),
        )

    warnings.extend(observed.warnings)
    return DiagnosticsSnapshot(
        setup=setup,
        database=DatabaseDiagnostic(DatabaseState.READABLE, database_path),
        schema=observed.schema,
        **snapshot_config,
        chunks=observed.chunks,
        sources=observed.sources,
        orphans=observed.orphans,
        dense_coverage=observed.dense_coverage,
        embedding=observed.embedding,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True, slots=True)
class _DatabaseObservation:
    schema: SchemaDiagnostic
    chunks: int | None
    sources: int | None
    orphans: int | None
    dense_coverage: DenseCoverage | None
    embedding: EmbeddingDiagnostic
    warnings: tuple[UserSafeWarning, ...]


def _read_database(database_path: Path, config: Mem2MemConfig) -> _DatabaseObservation:
    warnings: list[UserSafeWarning] = []
    # A quiescent WAL database does not need lock coordination.  Marking that
    # case immutable prevents SQLite from creating empty ``-wal``/``-shm``
    # sidecars merely because Home inspected it.  When a WAL file is present,
    # retain normal read-only locking so committed WAL rows remain visible.
    wal_path = database_path.with_name(f"{database_path.name}-wal")
    immutable = "&immutable=1" if not wal_path.exists() else ""
    uri = f"{database_path.as_uri()}?mode=ro{immutable}"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as database:
        database.execute("PRAGMA query_only=ON")
        tables = {
            str(row[0])
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        missing_tables = tuple(sorted(_REQUIRED_TABLES - tables))
        indexes = {
            str(row[0])
            for row in database.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        missing_indexes = tuple(sorted(_REQUIRED_INDEXES - indexes))
        chunk_columns: set[str] = set()
        if "chunks" in tables:
            chunk_columns = {str(row[1]) for row in database.execute("PRAGMA table_info('chunks')")}
        missing_columns = tuple(
            f"chunks.{column}" for column in sorted(_REQUIRED_CHUNK_COLUMNS - chunk_columns)
        )
        if "session_events" in tables:
            session_event_columns = {
                str(row[1]) for row in database.execute("PRAGMA table_info('session_events')")
            }
            if "metadata" not in session_event_columns:
                missing_columns = (*missing_columns, "session_events.metadata")
        pending_migrations: tuple[str, ...] = ()
        if "_memtomem_meta" in tables:
            backfill_done = database.execute(
                "SELECT 1 FROM _memtomem_meta WHERE key=?",
                (_CHUNK_LINKS_BACKFILL_KEY,),
            ).fetchone()
            if backfill_done is None:
                pending_migrations = (_CHUNK_LINKS_BACKFILL_KEY,)
        if missing_tables or missing_columns or missing_indexes or pending_migrations:
            schema = SchemaDiagnostic(
                SchemaState.MIGRATION_REQUIRED,
                missing_tables=missing_tables,
                missing_columns=missing_columns,
                missing_indexes=missing_indexes,
                pending_migrations=pending_migrations,
            )
            warnings.append(
                UserSafeWarning(
                    code="diagnostics.schema_migration_required",
                    message="The search database requires schema initialization or migration.",
                    recovery_action="Starting Search may initialize or migrate this database.",
                )
            )
        else:
            schema = SchemaDiagnostic(SchemaState.READY)

        chunks, sources, source_files = _read_chunk_counts(database, chunk_columns)
        orphans = _count_orphans(source_files) if source_files is not None else None
        if orphans:
            warnings.append(
                UserSafeWarning(
                    code="diagnostics.orphan_sources",
                    message=f"{orphans} indexed source path(s) are no longer present.",
                    recovery_action="Review orphan cleanup from a maintenance workflow.",
                )
            )

        dense_coverage = _read_dense_coverage(database, tables, chunks, warnings)
        embedding = _read_embedding(database, tables, config, warnings)

    return _DatabaseObservation(
        schema=schema,
        chunks=chunks,
        sources=sources,
        orphans=orphans,
        dense_coverage=dense_coverage,
        embedding=embedding,
        warnings=tuple(warnings),
    )


def _read_chunk_counts(
    database: sqlite3.Connection,
    chunk_columns: set[str],
) -> tuple[int | None, int | None, tuple[str, ...] | None]:
    if not {"source_file"}.issubset(chunk_columns):
        return None, None, None
    chunks = int(database.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    rows = tuple(str(row[0]) for row in database.execute("SELECT DISTINCT source_file FROM chunks"))
    return chunks, len(rows), rows


def _count_orphans(source_files: tuple[str, ...]) -> int:
    count = 0
    for source_file in source_files:
        if not source_file:
            count += 1
            continue
        try:
            exists = Path(source_file).expanduser().exists()
        except (OSError, ValueError):
            exists = False
        if not exists:
            count += 1
    return count


def _read_dense_coverage(
    database: sqlite3.Connection,
    tables: set[str],
    chunks: int | None,
    warnings: list[UserSafeWarning],
) -> DenseCoverage | None:
    if chunks is None:
        return None
    if "chunks_vec" not in tables:
        coverage = DenseCoverage(total=chunks, with_dense=0)
    else:
        try:
            import sqlite_vec

            database.enable_load_extension(True)
            try:
                sqlite_vec.load(database)
            finally:
                database.enable_load_extension(False)
            with_dense = int(
                database.execute(
                    "SELECT COUNT(*) FROM chunks c INNER JOIN chunks_vec v ON v.rowid = c.rowid"
                ).fetchone()[0]
            )
            coverage = DenseCoverage(total=chunks, with_dense=min(chunks, with_dense))
        except (ImportError, sqlite3.Error):
            warnings.append(
                UserSafeWarning(
                    code="diagnostics.dense_coverage_unavailable",
                    message="Dense-vector coverage could not be inspected safely.",
                    recovery_action="BM25 status remains available; inspect dense search later.",
                )
            )
            return None

    if coverage.missing:
        warnings.append(
            UserSafeWarning(
                code="diagnostics.dense_coverage_incomplete",
                message=(
                    f"Dense vectors cover {coverage.with_dense} of {coverage.total} chunks; "
                    "BM25 retrieval remains available."
                ),
                recovery_action="Build embeddings explicitly only if dense retrieval is expected.",
            )
        )
    return coverage


def _configured_embedding(config: Mem2MemConfig) -> EmbeddingDiagnostic:
    return EmbeddingDiagnostic(
        configured_dimension=int(config.embedding.dimension),
        configured_provider=str(config.embedding.provider),
        configured_model=str(config.embedding.model),
        stored_dimension=None,
        stored_provider=None,
        stored_model=None,
        dimension_mismatch=False,
        model_mismatch=False,
    )


def _snapshot_config(config: Mem2MemConfig) -> _SnapshotConfig:
    return {
        "storage_backend": str(config.storage.backend),
        "default_top_k": int(config.search.default_top_k),
        "rrf_k": int(config.search.rrf_k),
        "tokenizer": str(config.search.tokenizer),
        "scheduler_enabled": bool(config.scheduler.enabled),
        "health_watchdog_enabled": bool(config.health_watchdog.enabled),
    }


def _read_embedding(
    database: sqlite3.Connection,
    tables: set[str],
    config: Mem2MemConfig,
    warnings: list[UserSafeWarning],
) -> EmbeddingDiagnostic:
    stored: dict[str, str] = {}
    if "_memtomem_meta" in tables:
        stored = {
            str(key): str(value)
            for key, value in database.execute(
                "SELECT key, value FROM _memtomem_meta "
                "WHERE key IN ('embedding_dimension', 'embedding_provider', 'embedding_model')"
            )
        }
    stored_dimension: int | None = None
    raw_dimension = stored.get("embedding_dimension")
    if raw_dimension is not None:
        try:
            stored_dimension = int(raw_dimension)
        except ValueError:
            warnings.append(
                UserSafeWarning(
                    code="diagnostics.embedding_metadata_invalid",
                    message="Stored embedding metadata is invalid.",
                    recovery_action="Review embedding maintenance before dense search.",
                )
            )

    configured_dimension = int(config.embedding.dimension)
    configured_provider = str(config.embedding.provider)
    configured_model = str(config.embedding.model)
    stored_provider = stored.get("embedding_provider")
    stored_model = stored.get("embedding_model")
    dimension_mismatch = stored_dimension is not None and (
        stored_dimension != configured_dimension
        or (stored_dimension == 0 and configured_provider.lower() not in {"", "none"})
    )
    model_mismatch = bool(
        stored_provider is not None
        and stored_model is not None
        and configured_provider
        and configured_model
        and (stored_provider != configured_provider or stored_model != configured_model)
    )
    diagnostic = EmbeddingDiagnostic(
        configured_dimension=configured_dimension,
        configured_provider=configured_provider,
        configured_model=configured_model,
        stored_dimension=stored_dimension,
        stored_provider=stored_provider,
        stored_model=stored_model,
        dimension_mismatch=dimension_mismatch,
        model_mismatch=model_mismatch,
    )
    if diagnostic.mismatch:
        warnings.append(
            UserSafeWarning(
                code="diagnostics.embedding_mismatch",
                message="Stored and configured embedding settings do not match.",
                recovery_action="Resolve the mismatch explicitly before relying on dense search.",
            )
        )
    return diagnostic


__all__ = [
    "DatabaseDiagnostic",
    "DatabaseState",
    "DenseCoverage",
    "DiagnosticsSnapshot",
    "EmbeddingDiagnostic",
    "ReadOnlyDiagnosticsService",
    "SchemaDiagnostic",
    "SchemaState",
    "SetupDiagnostic",
    "SetupState",
    "inspect_read_only_diagnostics",
]
