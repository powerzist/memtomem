"""Pins the eleven pre-rebuild CLI behavior conflicts without resolving them.

These tests intentionally characterize current implementation seams. They are
not desired-behavior tests. A gate's pin should be replaced by the approved TUI
contract test when that workflow is implemented.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import click

from memtomem.cli import agent_cmd, config_cmd, context_cmd, embedding_cmd, memory
from memtomem.cli import memory_doctor_cmd, reset_cmd, session_cmd
from memtomem.indexing.engine import IndexEngine
from memtomem.server.component_factory import create_components
from memtomem.server.tools.status_config import _revert_to_stored
from memtomem.storage.sqlite_backend import SqliteBackend


CLI_ROOT = Path(__file__).resolve().parents[1] / "src" / "memtomem" / "cli"


def _callback(command: click.Command):
    assert command.callback is not None
    return command.callback


def test_gate_1_tokenizer_rebuild_calls_async_method_without_await() -> None:
    source = inspect.getsource(_callback(config_cmd.config_set))
    assert "count = storage.rebuild_fts()" in source
    assert "count = await storage.rebuild_fts()" not in source
    assert inspect.iscoroutinefunction(SqliteBackend.rebuild_fts)


def test_gate_2_config_set_omits_config_d_merge_used_by_show() -> None:
    show_source = inspect.getsource(_callback(config_cmd.config_show))
    set_source = inspect.getsource(_callback(config_cmd.config_set))
    assert "load_config_d(cfg)" in show_source
    assert "load_config_d" not in set_source
    assert "load_config_overrides(cfg)" in set_source


def test_gate_3_cli_revert_only_reports_while_mcp_swaps_runtime() -> None:
    cli_source = inspect.getsource(embedding_cmd._run)
    mcp_source = inspect.getsource(_revert_to_stored)
    cli_revert = cli_source[cli_source.index('elif internal_mode == "revert_to_stored"') :]
    assert "config.embedding.provider =" not in cli_revert
    assert "create_embedder" not in cli_revert
    assert "config.embedding.provider = stored" in mcp_source
    assert "comp.search_pipeline = SearchPipeline" in mcp_source
    assert "comp.index_engine = IndexEngine" in mcp_source


def test_gate_4_reset_short_circuits_on_chunk_count_before_reset_all() -> None:
    source = inspect.getsource(reset_cmd._run)
    short_circuit = source.index("if total == 0:")
    reset_call = source.index("await storage.reset_all()")
    assert short_circuit < reset_call
    assert "return" in source[short_circuit:reset_call]


def test_gate_5_stream_index_omits_non_stream_root_gate() -> None:
    non_stream = inspect.getsource(IndexEngine._index_path_inner)
    stream = inspect.getsource(IndexEngine.index_path_stream)
    assert "if not self._is_within_memory_dirs(path):" in non_stream
    assert "if not self._is_within_memory_dirs(path):" not in stream


def test_gate_6_cli_cache_invalidation_is_limited_to_selected_mutations() -> None:
    call_sites = []
    needle = ".search_pipeline.invalidate_cache()"
    for path in sorted(CLI_ROOT.glob("*.py")):
        if needle in path.read_text(encoding="utf-8"):
            call_sites.append(path.name)
    assert call_sites == ["context_cmd.py", "ingest_cmd.py"]


def test_gate_7_current_session_state_is_direct_write_and_unlink() -> None:
    write_source = inspect.getsource(session_cmd._write_current_session)
    clear_source = inspect.getsource(session_cmd._clear_current_session)
    assert ".write_text(" in write_source
    assert "atomic" not in write_source
    assert ".unlink()" in clear_source


def test_gate_8_add_and_share_append_before_index_and_tag_update() -> None:
    add_source = inspect.getsource(memory._add)
    share_source = inspect.getsource(agent_cmd._run_share)
    assert add_source.index("append_entry(") < add_source.index("index_file(")
    assert add_source.index("index_file(") < add_source.index("upsert_chunks(")
    assert share_source.index("append_entry(") < share_source.index("index_file(")


def test_gate_9_normal_bootstrap_mutates_but_doctor_is_read_only() -> None:
    bootstrap = inspect.getsource(create_components)
    config_reader = inspect.getsource(memory_doctor_cmd._load_config_read_only)
    db_reader = inspect.getsource(memory_doctor_cmd._read_source_signals)
    assert "await storage.initialize()" in bootstrap
    assert "load_config_overrides(config, migrate=False)" in config_reader
    assert "?mode=ro" in db_reader
    assert "PRAGMA query_only=ON" in db_reader


def test_gate_10_yes_without_apply_differs_between_context_migrations() -> None:
    general = inspect.getsource(_callback(context_cmd.migrate_cmd))
    settings = inspect.getsource(_callback(context_cmd.settings_migrate_cmd))
    memory_migrate = inspect.getsource(_callback(context_cmd.memory_migrate_cmd))
    assert "if (force or yes) and not apply_:" in general
    assert "if not apply_:" in settings
    assert "yes and not apply_" not in settings
    assert "yes and not apply_" not in memory_migrate


def test_gate_11_agent_migrate_applies_unless_dry_run_is_set() -> None:
    dry_run = next(param for param in agent_cmd.migrate.params if param.name == "dry_run")
    source = inspect.getsource(agent_cmd._run_migrate)
    assert dry_run.default is False
    assert source.index("if dry_run:") < source.index("rename_namespace(")
