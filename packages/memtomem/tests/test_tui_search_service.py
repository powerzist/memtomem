"""Focused tests for the Phase 4 TUI Search application service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from memtomem.models import Chunk, ChunkMetadata, ChunkType, SearchResult
from memtomem.search.pipeline import RetrievalStats
from memtomem.tui.application.contracts import OperationStatus
from memtomem.tui.application.search import SearchRequest, SearchService
from memtomem.tui.runtime import TuiPaths


class _Storage:
    def __init__(self, *, indexed_chunks: int = 1, dense_chunks: int = 1) -> None:
        self.indexed_chunks = indexed_chunks
        self.dense_chunks = dense_chunks

    async def get_stats(self) -> dict[str, int]:
        return {"total_chunks": self.indexed_chunks, "total_sources": 1}

    async def get_dense_coverage(self) -> dict[str, int]:
        return {"total": self.indexed_chunks, "with_dense": self.dense_chunks}


class _Pipeline:
    def __init__(
        self,
        results: list[SearchResult],
        stats: RetrievalStats,
        *,
        error: Exception | None = None,
    ) -> None:
        self.results = results
        self.stats = stats
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def search(self, query: str, **kwargs: object):
        self.calls.append((query, kwargs))
        if self.error is not None:
            raise self.error
        return self.results, self.stats


class _Runtime:
    def __init__(
        self,
        components: object,
        *,
        started: bool = False,
        config_path: Path = Path(__file__),
        is_dev: bool = False,
        paths: object | None = None,
    ) -> None:
        self.components = components
        self.started = started
        self.paths = paths or SimpleNamespace(config_path=config_path, is_dev=is_dev)
        self.lease_calls = 0

    @asynccontextmanager
    async def lease(self):
        self.lease_calls += 1
        self.started = True
        yield SimpleNamespace(components=self.components)


def _result() -> SearchResult:
    created = datetime(2026, 7, 1, tzinfo=timezone.utc)
    updated = datetime(2026, 7, 2, tzinfo=timezone.utc)
    chunk = Chunk(
        id=uuid4(),
        content="Complete original memory content.",
        created_at=created,
        updated_at=updated,
        metadata=ChunkMetadata(
            source_file=Path("notes/search.md"),
            heading_hierarchy=("# Search", "## Result"),
            chunk_type=ChunkType.MARKDOWN_SECTION,
            start_line=4,
            end_line=8,
            language="ko",
            tags=("phase4", "tui"),
            namespace="project",
            scope="project_local",
            project_root=Path("C:/workspace/project"),
            valid_from_unix=1_700_000_000,
            valid_to_unix=1_800_000_000,
        ),
    )
    return SearchResult(
        chunk=chunk,
        rank=1,
        score=0.875,
        source="reranked",
        via_session_summary=True,
    )


def _components(
    pipeline: _Pipeline,
    storage: _Storage,
    *,
    enable_bm25: bool = True,
    enable_dense: bool = True,
    project_memory_dirs: list[Path] | None = None,
    embedding_broken: dict[str, object] | None = None,
) -> object:
    return SimpleNamespace(
        config=SimpleNamespace(
            indexing=SimpleNamespace(project_memory_dirs=project_memory_dirs or []),
            search=SimpleNamespace(
                enable_bm25=enable_bm25,
                enable_dense=enable_dense,
            ),
        ),
        search_pipeline=pipeline,
        storage=storage,
        embedding_broken=embedding_broken,
    )


def _service(runtime: _Runtime, *, cwd: Path | None = None) -> SearchService:
    return SearchService(  # type: ignore[arg-type]
        runtime,
        cwd_getter=(lambda: cwd) if cwd is not None else Path.cwd,
        default_top_k_loader=lambda _paths: 10,
    )


def test_raw_top_k_matches_cli_integer_conversion_without_range_policy() -> None:
    assert SearchRequest.from_raw("query").top_k is None
    assert SearchRequest.from_raw("query", "-4").top_k == -4
    assert SearchRequest.from_raw("query", "0").top_k == 0
    with pytest.raises(ValueError):
        SearchRequest.from_raw("query", "not-an-integer")


def test_preflight_reads_effective_default_top_k_without_mutating_config(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / ".memtomem"
    state_root.mkdir()
    config_path = state_root / "config.json"
    config_path.write_text('{"search": {"default_top_k": 37}}\n', encoding="utf-8")
    paths = TuiPaths(
        mode="normal",
        project_root=None,
        state_root=state_root,
        config_path=config_path,
        config_d_path=state_root / "config.d",
        database_path=state_root / "memtomem.db",
        memories_path=state_root / "memories",
    )
    before = config_path.read_bytes()
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(_components(pipeline, _Storage()), paths=paths)

    preflight = SearchService(runtime).preflight()  # type: ignore[arg-type]

    assert preflight.default_top_k == 37
    assert config_path.read_bytes() == before
    assert not paths.database_path.exists()


async def test_malformed_config_blocks_preflight_and_runtime_bootstrap(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / ".memtomem"
    state_root.mkdir()
    config_path = state_root / "config.json"
    config_path.write_text('{"search": ', encoding="utf-8")
    paths = TuiPaths(
        mode="normal",
        project_root=None,
        state_root=state_root,
        config_path=config_path,
        config_d_path=state_root / "config.d",
        database_path=state_root / "memtomem.db",
        memories_path=state_root / "memories",
    )
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(_components(pipeline, _Storage()), paths=paths)
    service = SearchService(runtime)  # type: ignore[arg-type]

    preflight = service.preflight()
    result = await service.execute(SearchRequest(query="memory", allow_runtime_initialization=True))

    assert preflight.setup_required is False
    assert preflight.requires_consent is False
    assert preflight.may_initialize_storage is False
    assert preflight.may_migrate_schema is False
    assert preflight.default_top_k is None
    assert preflight.readiness_error is not None
    assert preflight.readiness_error.code == "search.config-unreadable"
    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.config-unreadable"
    assert runtime.lease_calls == 0
    assert pipeline.calls == []
    assert not paths.database_path.exists()


async def test_invalid_known_config_value_blocks_search_preflight(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / ".memtomem"
    state_root.mkdir()
    config_path = state_root / "config.json"
    config_path.write_text(
        '{"search": {"default_top_k": "not-an-integer"}}\n',
        encoding="utf-8",
    )
    paths = TuiPaths(
        mode="normal",
        project_root=None,
        state_root=state_root,
        config_path=config_path,
        config_d_path=state_root / "config.d",
        database_path=state_root / "memtomem.db",
        memories_path=state_root / "memories",
    )
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(_components(pipeline, _Storage()), paths=paths)
    service = SearchService(runtime)  # type: ignore[arg-type]

    preflight = service.preflight()
    result = await service.execute(SearchRequest(query="memory", allow_runtime_initialization=True))

    assert preflight.readiness_error is not None
    assert preflight.readiness_error.code == "search.config-unreadable"
    assert preflight.requires_consent is False
    assert preflight.may_initialize_storage is False
    assert preflight.may_migrate_schema is False
    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.config-unreadable"
    assert runtime.lease_calls == 0
    assert pipeline.calls == []
    assert not paths.database_path.exists()


async def test_preflight_and_missing_consent_do_not_start_runtime() -> None:
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(_components(pipeline, _Storage()))
    service = _service(runtime)

    preflight = service.preflight()
    result = await service.execute(SearchRequest(query="memory"))

    assert preflight.requires_consent is True
    assert preflight.setup_required is False
    assert preflight.may_initialize_storage is True
    assert preflight.may_migrate_schema is True
    assert preflight.may_migrate_config is True
    assert preflight.may_rewrite_config_file is True
    assert "migrate legacy configuration" in preflight.message
    assert "rewrite config.json" in preflight.message
    assert preflight.auto_index is False
    assert preflight.auto_build_missing_embeddings is False
    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.runtime-consent-required"
    assert runtime.lease_calls == 0
    assert pipeline.calls == []


def test_dev_preflight_does_not_claim_normal_config_rewrite() -> None:
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(
        _components(pipeline, _Storage()),
        is_dev=True,
    )

    preflight = _service(runtime).preflight()

    assert preflight.requires_consent is True
    assert preflight.may_migrate_config is False
    assert preflight.may_rewrite_config_file is False
    assert "rewrite config.json" not in preflight.message


async def test_invalid_as_of_is_rejected_before_runtime_initialization() -> None:
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(_components(pipeline, _Storage()))
    service = _service(runtime)

    result = await service.execute(
        SearchRequest(
            query="memory",
            as_of="2026-Q5",
            allow_runtime_initialization=True,
        )
    )

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.invalid-as-of"
    assert runtime.lease_calls == 0


async def test_as_of_whitespace_is_not_trimmed_into_a_valid_cli_value() -> None:
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(_components(pipeline, _Storage()))

    result = await _service(runtime).execute(
        SearchRequest(
            query="memory",
            as_of=" 2026-Q2 ",
            allow_runtime_initialization=True,
        )
    )

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.invalid-as-of"
    assert runtime.lease_calls == 0


async def test_missing_config_is_setup_required_without_touching_runtime(tmp_path: Path) -> None:
    config_path = tmp_path / "state" / "config.json"
    pipeline = _Pipeline([_result()], RetrievalStats(final_total=1))
    runtime = _Runtime(
        _components(pipeline, _Storage()),
        config_path=config_path,
    )
    service = _service(runtime)

    preflight = service.preflight()
    result = await service.execute(SearchRequest(query="memory", allow_runtime_initialization=True))

    assert preflight.setup_required is True
    assert preflight.requires_consent is False
    assert preflight.may_initialize_storage is False
    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.setup-required"
    assert runtime.lease_calls == 0
    assert pipeline.calls == []
    assert config_path.parent.exists() is False


async def test_execute_forwards_cli_filters_and_detaches_complete_result(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_memory_dir = project_root / ".memtomem" / "memories.local"
    cwd = project_root / "src" / "package"
    pipeline = _Pipeline(
        [_result()],
        RetrievalStats(
            bm25_candidates=7,
            dense_candidates=6,
            fused_total=4,
            final_total=1,
            hidden_system_ns=2,
        ),
    )
    runtime = _Runtime(
        _components(
            pipeline,
            _Storage(indexed_chunks=9, dense_chunks=9),
            project_memory_dirs=[project_memory_dir],
        )
    )
    service = _service(runtime, cwd=cwd)
    request = SearchRequest.from_raw(
        "  exact query  ",
        "-3",
        source_filter=" notes/ ",
        tag_filter="one,two",
        namespace="project",
        scope="project_local,project_shared",
        as_of="2026-Q2",
        allow_runtime_initialization=True,
    )

    result = await service.execute(request)

    assert result.status is OperationStatus.SUCCEEDED
    assert result.value is not None
    assert result.value.project_context_root == str(project_root.resolve())
    assert result.value.stats.bm25_candidates == 7
    assert result.value.stats.dense_candidates == 6
    assert result.value.stats.indexed_chunks == 9
    assert result.value.stats.dense_chunks == 9
    assert [warning.code for warning in result.warnings] == ["search.system-namespaces-hidden"]
    item = result.value.items[0]
    assert item.content == "Complete original memory content."
    assert item.tags == ("phase4", "tui")
    assert item.created_at == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert item.updated_at == datetime(2026, 7, 2, tzinfo=timezone.utc)
    assert item.via_session_summary is True

    query, kwargs = pipeline.calls[0]
    assert query == "  exact query  "
    assert kwargs == {
        "top_k": -3,
        "source_filter": " notes/ ",
        "tag_filter": "one,two",
        "namespace": "project",
        "as_of_unix": 1_775_001_600,
        "scope": "project_local,project_shared",
        "project_context_root": project_root.resolve(),
    }
    spec = service.operation_spec(request)
    assert spec.cancellable is False
    assert spec.exit_policy.value == "wait"
    assert spec.safe_parameters == (("top_k", "-3"),)


@pytest.mark.parametrize(
    "query,source_filter,tag_filter",
    [
        ("", None, None),
        ("   ", None, "phase4"),
        ("", "notes/", None),
    ],
)
async def test_blank_query_preserves_core_filter_only_and_empty_result_meaning(
    query: str,
    source_filter: str | None,
    tag_filter: str | None,
) -> None:
    pipeline = _Pipeline([], RetrievalStats())
    runtime = _Runtime(
        _components(pipeline, _Storage(indexed_chunks=2, dense_chunks=2)),
        started=True,
    )

    result = await _service(runtime).execute(
        SearchRequest(
            query=query,
            source_filter=source_filter,
            tag_filter=tag_filter,
        )
    )

    assert result.status is OperationStatus.SUCCEEDED
    assert pipeline.calls[0][0] == query
    assert pipeline.calls[0][1]["source_filter"] == source_filter
    assert pipeline.calls[0][1]["tag_filter"] == tag_filter


async def test_filter_only_results_bypass_retriever_and_embedding_classification() -> None:
    pipeline = _Pipeline(
        [_result()],
        RetrievalStats(
            final_total=1,
            bm25_error="unused keyword path",
            dense_error="unused dense path",
            rerank_error="unused reranker path",
        ),
    )
    runtime = _Runtime(
        _components(
            pipeline,
            _Storage(indexed_chunks=2, dense_chunks=0),
            enable_bm25=False,
            enable_dense=False,
            embedding_broken={"reason": "unused by filter-only"},
        ),
        started=True,
    )

    result = await _service(runtime).execute(SearchRequest(query="   ", tag_filter="phase4"))

    assert result.status is OperationStatus.SUCCEEDED
    assert result.value is not None
    assert result.value.items[0].content == "Complete original memory content."
    assert result.warnings == ()


async def test_blank_query_without_filters_preserves_core_success_before_readiness() -> None:
    pipeline = _Pipeline([], RetrievalStats())
    runtime = _Runtime(
        _components(
            pipeline,
            _Storage(indexed_chunks=0, dense_chunks=0),
            enable_bm25=False,
            enable_dense=False,
            embedding_broken={"reason": "unused by blank query"},
        ),
        started=True,
    )

    result = await _service(runtime).execute(SearchRequest(query="   "))

    assert result.status is OperationStatus.SUCCEEDED
    assert result.value is not None
    assert result.value.items == ()
    assert result.warnings == ()


async def test_bm25_only_ignores_embedding_mismatch_and_dense_coverage() -> None:
    pipeline = _Pipeline(
        [_result()],
        RetrievalStats(bm25_candidates=1, fused_total=1, final_total=1),
    )
    runtime = _Runtime(
        _components(
            pipeline,
            _Storage(indexed_chunks=2, dense_chunks=0),
            enable_bm25=True,
            enable_dense=False,
            embedding_broken={"reason": "dense mismatch"},
        ),
        started=True,
    )

    result = await _service(runtime).execute(SearchRequest(query="memory"))

    assert result.status is OperationStatus.SUCCEEDED
    assert result.value is not None
    assert result.warnings == ()


async def test_each_single_leg_and_reranker_degradation_is_structured() -> None:
    pipeline = _Pipeline(
        [_result()],
        RetrievalStats(
            dense_candidates=1,
            fused_total=1,
            final_total=1,
            bm25_error="database-internal-detail",
            rerank_error="provider-secret-detail",
        ),
    )
    runtime = _Runtime(
        _components(
            pipeline,
            _Storage(indexed_chunks=2, dense_chunks=1),
        ),
        started=True,
    )

    result = await _service(runtime).execute(SearchRequest(query="memory"))

    assert result.status is OperationStatus.PARTIAL
    assert result.value is not None
    codes = {warning.code for warning in result.warnings}
    assert codes == {
        "search.bm25-degraded",
        "search.reranker-degraded",
        "search.dense-coverage-incomplete",
    }
    assert "database-internal-detail" not in repr(result)
    assert "provider-secret-detail" not in repr(result)


async def test_all_enabled_retrievers_failing_is_total_failure() -> None:
    pipeline = _Pipeline(
        [],
        RetrievalStats(
            bm25_error="fts unavailable",
            dense_error="embedder unavailable",
        ),
    )
    runtime = _Runtime(
        _components(pipeline, _Storage(indexed_chunks=3, dense_chunks=0)),
        started=True,
    )

    result = await _service(runtime).execute(SearchRequest(query="memory"))

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.retrieval-failed"
    assert {warning.code for warning in result.warnings} >= {
        "search.bm25-degraded",
        "search.dense-degraded",
    }


async def test_dense_only_with_no_stored_vectors_is_total_failure_without_backfill() -> None:
    pipeline = _Pipeline([], RetrievalStats())
    storage = _Storage(indexed_chunks=3, dense_chunks=0)
    runtime = _Runtime(
        _components(
            pipeline,
            storage,
            enable_bm25=False,
            enable_dense=True,
        ),
        started=True,
    )

    result = await _service(runtime).execute(SearchRequest(query="memory"))

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.retrieval-failed"
    assert {warning.code for warning in result.warnings} == {"search.dense-coverage-incomplete"}
    assert not hasattr(storage, "build_missing_embeddings")


async def test_empty_index_is_actionable_and_never_repaired() -> None:
    pipeline = _Pipeline([], RetrievalStats())
    storage = _Storage(indexed_chunks=0, dense_chunks=0)
    runtime = _Runtime(_components(pipeline, storage), started=True)

    result = await _service(runtime).execute(SearchRequest(query="memory"))

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.index-empty"
    assert not hasattr(storage, "index")


async def test_unexpected_pipeline_error_is_not_exposed() -> None:
    pipeline = _Pipeline([], RetrievalStats(), error=RuntimeError("secret-token"))
    runtime = _Runtime(_components(pipeline, _Storage()), started=True)

    result = await _service(runtime).execute(SearchRequest(query="memory"))

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "search.failed"
    assert "secret-token" not in repr(result)
