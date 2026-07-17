"""Search-cache lifecycle contracts used by the persistent TUI runtime."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from memtomem.config import SearchConfig
from memtomem.models import Chunk, ChunkMetadata, SearchResult
from memtomem.search.pipeline import SearchPipeline


def _result(content: str = "cached") -> SearchResult:
    return SearchResult(
        chunk=Chunk(
            content=content,
            metadata=ChunkMetadata(source_file=Path(f"/tmp/{content}.md")),
            id=uuid4(),
            embedding=[],
        ),
        score=1.0,
        rank=1,
        source="bm25",
    )


def _pipeline(*, bm25_side_effect: object | None = None) -> tuple[SearchPipeline, AsyncMock]:
    storage = AsyncMock()
    if bm25_side_effect is None:
        storage.bm25_search = AsyncMock(return_value=[_result()])
    else:
        storage.bm25_search = AsyncMock(side_effect=bm25_side_effect)
    storage.dense_search = AsyncMock(return_value=[])
    storage.increment_access = AsyncMock()
    storage.save_query_history = AsyncMock()
    storage.get_access_counts = AsyncMock(return_value={})
    storage.get_embeddings_for_chunks = AsyncMock(return_value={})
    storage.get_importance_scores = AsyncMock(return_value={})
    storage.count_chunks_by_ns_prefix = AsyncMock(return_value=0)

    embedder = AsyncMock()
    embedder.embed_query = AsyncMock(return_value=[0.1] * 8)
    pipeline = SearchPipeline(
        storage=storage,
        embedder=embedder,
        config=SearchConfig(enable_bm25=True, enable_dense=False),
    )
    return pipeline, storage


def test_result_only_invalidation_retains_query_expansion_cache() -> None:
    pipeline, _ = _pipeline()
    pipeline._search_cache["key"] = (0.0, pipeline._cache_version, [], AsyncMock())
    pipeline._expansion_cache["query"] = "expanded query"

    prior_version = pipeline._cache_version
    pipeline.invalidate_result_cache()

    assert pipeline._search_cache == {}
    assert pipeline._cache_version == prior_version + 1
    assert pipeline._expansion_cache == {"query": "expanded query"}

    pipeline.invalidate_cache()
    assert pipeline._expansion_cache == {}


def test_result_cache_suspension_is_nested_and_does_not_invalidate() -> None:
    pipeline, _ = _pipeline()
    pipeline._search_cache["warm"] = (0.0, pipeline._cache_version, [], AsyncMock())
    prior_version = pipeline._cache_version

    with pipeline.suspend_result_cache():
        assert pipeline.result_cache_suspended
        with pipeline.suspend_result_cache():
            assert pipeline.result_cache_suspended
        assert pipeline.result_cache_suspended

    assert not pipeline.result_cache_suspended
    assert "warm" in pipeline._search_cache
    assert pipeline._cache_version == prior_version


@pytest.mark.asyncio
async def test_no_change_window_bypasses_cache_but_preserves_warm_result() -> None:
    pipeline, storage = _pipeline()

    first, _ = await pipeline.search("same query", top_k=1)
    assert storage.bm25_search.await_count == 1
    cache_snapshot = dict(pipeline._search_cache)
    version_snapshot = pipeline._cache_version

    with pipeline.suspend_result_cache():
        during, _ = await pipeline.search("same query", top_k=1)
        assert storage.bm25_search.await_count == 2
        assert pipeline._search_cache == cache_snapshot

    after, _ = await pipeline.search("same query", top_k=1)
    assert storage.bm25_search.await_count == 2
    assert pipeline._cache_version == version_snapshot
    assert first[0].chunk.id == after[0].chunk.id
    assert during


@pytest.mark.asyncio
async def test_changed_window_blocks_in_flight_stale_repopulation() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_search(*args: object, **kwargs: object) -> list[SearchResult]:
        started.set()
        await release.wait()
        return [_result("stale")]

    pipeline, _ = _pipeline(bm25_side_effect=delayed_search)
    search_task = asyncio.create_task(pipeline.search("concurrent query", top_k=1))
    await started.wait()

    with pipeline.suspend_result_cache():
        pipeline.invalidate_result_cache()

    release.set()
    results, _ = await search_task

    assert results
    assert pipeline._search_cache == {}


@pytest.mark.asyncio
async def test_changed_window_clears_results_but_retains_expansion_cache() -> None:
    pipeline, storage = _pipeline()
    await pipeline.search("same query", top_k=1)
    pipeline._expansion_cache["same query"] = "expanded"

    with pipeline.suspend_result_cache():
        pipeline.invalidate_result_cache()

    await pipeline.search("same query", top_k=1)
    assert storage.bm25_search.await_count == 2
    assert pipeline._expansion_cache == {"same query": "expanded"}
