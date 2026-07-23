"""Gate 9 regression tests for Home/Status read-only diagnostics."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from memtomem.config import StorageConfig
from memtomem.storage.sqlite_backend import SqliteBackend
from memtomem.tui.application.diagnostics import (
    DatabaseState,
    ReadOnlyDiagnosticsService,
    SchemaState,
    SetupState,
)
from memtomem.tui.application.runtime import RuntimeManager
from memtomem.tui.runtime import TuiPaths, load_tui_config_read_only


def _paths(tmp_path: Path) -> TuiPaths:
    state_root = tmp_path / ".dev" / ".memtomem"
    return TuiPaths(
        mode="dev",
        project_root=tmp_path,
        state_root=state_root,
        config_path=state_root / "config.json",
        config_d_path=state_root / "config.d",
        database_path=state_root / "memtomem.db",
        memories_path=state_root / "memories",
    )


def _write_config(
    paths: TuiPaths,
    *,
    provider: str = "none",
    model: str = "noop",
    dimension: int = 0,
    scheduler: bool = False,
    watchdog: bool = False,
) -> None:
    paths.config_path.parent.mkdir(parents=True, exist_ok=True)
    paths.config_path.write_text(
        json.dumps(
            {
                "embedding": {
                    "provider": provider,
                    "model": model,
                    "dimension": dimension,
                },
                "storage": {"backend": "sqlite", "sqlite_path": str(paths.database_path)},
                "indexing": {
                    "memory_dirs": [str(paths.memories_path)],
                    "auto_discover": True,
                },
                "search": {
                    "default_top_k": 23,
                    "rrf_k": 71,
                    "tokenizer": "unicode61",
                },
                "scheduler": {"enabled": scheduler},
                "health_watchdog": {"enabled": watchdog},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


async def _create_current_database(paths: TuiPaths) -> None:
    backend = SqliteBackend(
        StorageConfig(sqlite_path=paths.database_path),
        dimension=0,
        embedding_provider="none",
        embedding_model="noop",
    )
    await backend.initialize()
    await backend.close()


def _tree_fingerprint(root: Path) -> tuple[tuple[str, bytes, int], ...]:
    if not root.exists():
        return ()
    return tuple(
        (str(path.relative_to(root)), path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


async def test_missing_setup_and_database_create_nothing(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = RuntimeManager(paths)

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.setup.state is SetupState.REQUIRED
    assert snapshot.database.state is DatabaseState.MISSING
    assert snapshot.schema.state is SchemaState.UNAVAILABLE
    assert {warning.code for warning in snapshot.warnings} == {
        "diagnostics.database_missing",
        "diagnostics.setup_required",
    }
    assert not paths.state_root.exists()
    assert not manager.started
    await manager.close()


async def test_read_only_loader_disables_legacy_config_migration(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_config(paths)
    original = paths.config_path.read_bytes()

    config = load_tui_config_read_only(paths)

    assert config.indexing.auto_discover is True
    assert paths.config_path.read_bytes() == original


async def test_snapshot_preserves_files_and_reports_full_status_parity(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_config(
        paths,
        provider="fastembed",
        model="BAAI/bge-small-en-v1.5",
        dimension=384,
        scheduler=True,
        watchdog=False,
    )
    await _create_current_database(paths)
    paths.memories_path.mkdir(parents=True)
    present_source = paths.memories_path / "present.md"
    present_source.write_text("present\n", encoding="utf-8")
    missing_source = paths.memories_path / "missing.md"
    with closing(sqlite3.connect(paths.database_path)) as database:
        for index, source in enumerate((present_source, missing_source), start=1):
            cursor = database.execute(
                "INSERT INTO chunks "
                "(id, content, content_hash, source_file, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"chunk-{index}", f"content {index}", f"hash-{index}", str(source), "now", "now"),
            )
            database.execute(
                "INSERT INTO chunks_fts(rowid, content, source_file) VALUES (?, ?, ?)",
                (cursor.lastrowid, f"content {index}", str(source)),
            )
        database.commit()
    before = _tree_fingerprint(paths.state_root)
    manager = RuntimeManager(paths)

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.setup.state is SetupState.CONFIGURED
    assert snapshot.database.state is DatabaseState.READABLE
    assert snapshot.schema.state is SchemaState.READY
    assert snapshot.storage_backend == "sqlite"
    assert snapshot.default_top_k == 23
    assert snapshot.rrf_k == 71
    assert snapshot.tokenizer == "unicode61"
    assert snapshot.scheduler_enabled is True
    assert snapshot.health_watchdog_enabled is False
    assert snapshot.chunks == 2
    assert snapshot.sources == 2
    assert snapshot.orphans == 1
    assert snapshot.dense_coverage is not None
    assert snapshot.dense_coverage.total == 2
    assert snapshot.dense_coverage.with_dense == 0
    assert snapshot.dense_coverage.missing == 2
    assert snapshot.dense_coverage.ratio == 0.0
    assert snapshot.embedding is not None
    assert snapshot.embedding.stored_dimension == 0
    assert snapshot.embedding.configured_dimension == 384
    assert snapshot.embedding.mismatch
    assert {
        "diagnostics.dense_coverage_incomplete",
        "diagnostics.embedding_mismatch",
        "diagnostics.orphan_sources",
        "diagnostics.scheduler_inactive",
    }.issubset({warning.code for warning in snapshot.warnings})
    assert _tree_fingerprint(paths.state_root) == before
    assert not manager.started
    await manager.close()


async def test_legacy_database_is_reported_without_running_schema_migrations(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_config(paths)
    with closing(sqlite3.connect(paths.database_path)) as database:
        database.execute("CREATE TABLE _memtomem_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        database.execute(
            "CREATE TABLE chunks ("
            "id TEXT PRIMARY KEY, content TEXT NOT NULL, source_file TEXT NOT NULL)"
        )
        database.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(content, source_file)")
        database.commit()
    before = _tree_fingerprint(paths.state_root)

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.database.state is DatabaseState.READABLE
    assert snapshot.schema.state is SchemaState.MIGRATION_REQUIRED
    assert "access_log" in snapshot.schema.missing_tables
    assert "chunks.scope" in snapshot.schema.missing_columns
    assert "idx_chunks_unique_content" in snapshot.schema.missing_indexes
    assert "chunk_links_backfill_v1" in snapshot.schema.pending_migrations
    assert "diagnostics.schema_migration_required" in {
        warning.code for warning in snapshot.warnings
    }
    assert _tree_fingerprint(paths.state_root) == before


async def test_corrupt_database_is_structured_and_left_unchanged(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_config(paths)
    paths.database_path.write_bytes(b"not-a-sqlite-database\x00provider-secret")
    before = _tree_fingerprint(paths.state_root)

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.database.state is DatabaseState.UNREADABLE
    assert snapshot.schema.state is SchemaState.UNREADABLE
    assert snapshot.chunks is None
    assert {warning.code for warning in snapshot.warnings} == {"diagnostics.database_unreadable"}
    assert "provider-secret" not in snapshot.warnings[0].message
    assert _tree_fingerprint(paths.state_root) == before


async def test_config_failure_returns_only_user_safe_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)

    def fail_config(_paths: TuiPaths):
        raise RuntimeError("secret-provider-token")

    monkeypatch.setattr(
        "memtomem.tui.application.diagnostics.load_tui_config_read_only",
        fail_config,
    )

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.setup.state is SetupState.ERROR
    assert snapshot.schema.state is SchemaState.UNAVAILABLE
    assert len(snapshot.warnings) == 1
    assert snapshot.warnings[0].code == "diagnostics.config_unreadable"
    assert "secret-provider-token" not in snapshot.warnings[0].message
    assert "secret-provider-token" not in (snapshot.warnings[0].recovery_action or "")


async def test_malformed_config_file_is_structured_and_left_unchanged(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    paths.config_path.parent.mkdir(parents=True)
    paths.config_path.write_text('{"search": ', encoding="utf-8")
    before = _tree_fingerprint(paths.state_root)

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.setup.state is SetupState.ERROR
    assert snapshot.database.state is DatabaseState.UNREADABLE
    assert snapshot.schema.state is SchemaState.UNAVAILABLE
    assert {warning.code for warning in snapshot.warnings} == {"diagnostics.config_unreadable"}
    assert _tree_fingerprint(paths.state_root) == before


async def test_malformed_config_fragment_is_structured_and_left_unchanged(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_config(paths)
    paths.config_d_path.mkdir()
    (paths.config_d_path / "broken.json").write_text('{"search": ', encoding="utf-8")
    before = _tree_fingerprint(paths.state_root)

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.setup.state is SetupState.ERROR
    assert snapshot.database.state is DatabaseState.UNREADABLE
    assert snapshot.schema.state is SchemaState.UNAVAILABLE
    assert {warning.code for warning in snapshot.warnings} == {"diagnostics.config_unreadable"}
    assert _tree_fingerprint(paths.state_root) == before


@pytest.mark.parametrize("content", ["[]", "null", '{"storage": []}'])
async def test_structurally_invalid_config_fragments_are_blocked(
    tmp_path: Path,
    content: str,
) -> None:
    paths = _paths(tmp_path)
    _write_config(paths)
    paths.config_d_path.mkdir()
    fragment = paths.config_d_path / "broken.json"
    fragment.write_text(content, encoding="utf-8")
    before = _tree_fingerprint(paths.state_root)

    snapshot = await ReadOnlyDiagnosticsService(paths).inspect()

    assert snapshot.setup.state is SetupState.ERROR
    assert snapshot.database.state is DatabaseState.UNREADABLE
    assert snapshot.schema.state is SchemaState.UNAVAILABLE
    assert {warning.code for warning in snapshot.warnings} == {"diagnostics.config_unreadable"}
    assert _tree_fingerprint(paths.state_root) == before
