"""Tests for reranker pipeline components."""

import pytest
from pathlib import Path
from uuid import uuid4
from memtomem.models import Chunk, ChunkMetadata, SearchResult


def _make_result(content, score, rank=1):
    chunk = Chunk(
        content=content,
        metadata=ChunkMetadata(source_file=Path("/tmp/test.md")),
        id=uuid4(),
        embedding=[],
    )
    return SearchResult(chunk=chunk, score=score, rank=rank, source="fused")


class TestCohereReranker:
    def test_init(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.cohere import CohereReranker

        config = RerankConfig(enabled=True, provider="cohere", api_key="test-key")
        reranker = CohereReranker(config)
        assert reranker._config.api_key == "test-key"
        assert reranker._client is None

    @pytest.mark.asyncio
    async def test_empty_results(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.cohere import CohereReranker

        config = RerankConfig(enabled=True, provider="cohere", api_key="test")
        reranker = CohereReranker(config)
        result = await reranker.rerank("query", [], top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_failure_keeps_direct_fallback_and_reports_per_call_diagnostic(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.cohere import CohereReranker

        class BrokenClient:
            async def post(self, *_args, **_kwargs):
                raise RuntimeError("cohere unavailable")

        candidates = [_make_result("first", 1.0), _make_result("second", 0.5)]
        reranker = CohereReranker(RerankConfig(enabled=True, provider="cohere", api_key="test"))
        reranker._client = BrokenClient()  # type: ignore[assignment]

        assert await reranker.rerank("query", candidates, top_k=1) == candidates[:1]
        outcome = await reranker.rerank_with_diagnostics("query", candidates, top_k=1)
        assert list(outcome.results) == candidates[:1]
        assert outcome.error == "cohere unavailable"

    @pytest.mark.asyncio
    async def test_direct_client_setup_failure_still_propagates(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.cohere import CohereReranker

        candidates = [_make_result("first", 1.0)]
        reranker = CohereReranker(RerankConfig(enabled=True, provider="cohere", api_key="test"))

        def fail_client_setup():
            raise RuntimeError("client setup failed")

        reranker._get_client = fail_client_setup  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="client setup failed"):
            await reranker.rerank("query", candidates, top_k=1)
        outcome = await reranker.rerank_with_diagnostics("query", candidates, top_k=1)
        assert list(outcome.results) == candidates
        assert outcome.error == "client setup failed"

    @pytest.mark.asyncio
    async def test_direct_response_conversion_failure_still_propagates(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.cohere import CohereReranker

        class MalformedResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"results": [{"relevance_score": 0.5}]}

        class MalformedClient:
            async def post(self, *_args, **_kwargs):
                return MalformedResponse()

        candidates = [_make_result("first", 1.0)]
        reranker = CohereReranker(RerankConfig(enabled=True, provider="cohere", api_key="test"))
        reranker._client = MalformedClient()  # type: ignore[assignment]

        with pytest.raises(KeyError, match="index"):
            await reranker.rerank("query", candidates, top_k=1)
        outcome = await reranker.rerank_with_diagnostics("query", candidates, top_k=1)
        assert list(outcome.results) == candidates
        assert outcome.error is not None
        assert "index" in outcome.error

    @pytest.mark.asyncio
    async def test_close(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.cohere import CohereReranker

        config = RerankConfig(enabled=True, provider="cohere", api_key="test")
        reranker = CohereReranker(config)
        await reranker.close()
        assert reranker._client is None


class TestLocalReranker:
    def test_init(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.local import LocalReranker

        config = RerankConfig(
            enabled=True, provider="local", model="cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        reranker = LocalReranker(config)
        assert reranker._model is None  # lazy loaded

    @pytest.mark.asyncio
    async def test_empty_results(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.local import LocalReranker

        config = RerankConfig(enabled=True, provider="local")
        reranker = LocalReranker(config)
        result = await reranker.rerank("query", [], top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_failure_keeps_direct_fallback_and_reports_per_call_diagnostic(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.local import LocalReranker

        class BrokenModel:
            def predict(self, _pairs):
                raise RuntimeError("local model unavailable")

        candidates = [_make_result("first", 1.0), _make_result("second", 0.5)]
        reranker = LocalReranker(RerankConfig(enabled=True, provider="local"))
        reranker._model = BrokenModel()

        assert await reranker.rerank("query", candidates, top_k=1) == candidates[:1]
        outcome = await reranker.rerank_with_diagnostics("query", candidates, top_k=1)
        assert list(outcome.results) == candidates[:1]
        assert outcome.error == "local model unavailable"

    @pytest.mark.asyncio
    async def test_direct_model_setup_failure_still_propagates(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.local import LocalReranker

        candidates = [_make_result("first", 1.0)]
        reranker = LocalReranker(RerankConfig(enabled=True, provider="local"))

        def fail_model_setup():
            raise RuntimeError("model setup failed")

        reranker._get_model = fail_model_setup  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="model setup failed"):
            await reranker.rerank("query", candidates, top_k=1)
        outcome = await reranker.rerank_with_diagnostics("query", candidates, top_k=1)
        assert list(outcome.results) == candidates
        assert outcome.error == "model setup failed"

    @pytest.mark.asyncio
    async def test_direct_score_conversion_failure_still_propagates(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.local import LocalReranker

        class MalformedModel:
            def predict(self, _pairs):
                return ["not-a-score"]

        candidates = [_make_result("first", 1.0)]
        reranker = LocalReranker(RerankConfig(enabled=True, provider="local"))
        reranker._model = MalformedModel()

        with pytest.raises(ValueError, match="could not convert string to float"):
            await reranker.rerank("query", candidates, top_k=1)
        outcome = await reranker.rerank_with_diagnostics("query", candidates, top_k=1)
        assert list(outcome.results) == candidates
        assert outcome.error is not None
        assert "could not convert string to float" in outcome.error

    @pytest.mark.asyncio
    async def test_close(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.local import LocalReranker

        config = RerankConfig(enabled=True, provider="local")
        reranker = LocalReranker(config)
        await reranker.close()
        assert reranker._model is None


class TestRerankerFactory:
    def test_disabled(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.factory import create_reranker

        assert create_reranker(RerankConfig(enabled=False)) is None

    def test_cohere(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.factory import create_reranker
        from memtomem.search.reranker.cohere import CohereReranker

        r = create_reranker(RerankConfig(enabled=True, provider="cohere"))
        assert isinstance(r, CohereReranker)

    def test_local(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.factory import create_reranker
        from memtomem.search.reranker.local import LocalReranker

        r = create_reranker(RerankConfig(enabled=True, provider="local"))
        assert isinstance(r, LocalReranker)

    def test_unknown_raises(self):
        from memtomem.config import RerankConfig
        from memtomem.search.reranker.factory import create_reranker

        with pytest.raises(ValueError):
            create_reranker(RerankConfig(enabled=True, provider="unknown"))
