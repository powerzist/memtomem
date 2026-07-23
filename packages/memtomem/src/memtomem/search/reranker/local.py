"""Local cross-encoder reranker using sentence-transformers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from memtomem.search.reranker.base import RerankOutcome

if TYPE_CHECKING:
    from memtomem.config import RerankConfig
    from memtomem.models import SearchResult

logger = logging.getLogger(__name__)


class LocalReranker:
    """Cross-encoder reranking using a local sentence-transformers model."""

    def __init__(self, config: RerankConfig):
        self._config = config
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._config.model)
            logger.info("Loaded local reranker: %s", self._config.model)
        return self._model

    async def rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        """Rerank with the historical prediction-only fallback boundary."""
        if not results:
            return results

        # Model construction was outside the original fallback block. Keep
        # import, download, and setup failures visible to direct callers.
        model = self._get_model()
        pairs = [(query, result.chunk.content) for result in results]
        try:
            scores = model.predict(pairs)
        except Exception as exc:
            logger.warning("Local rerank failed, returning original order: %s", exc)
            return results[:top_k]
        # Sorting and float/result conversion were outside that block and must
        # continue to propagate malformed provider output to direct callers.
        return self._convert_results(scores, results, top_k)

    async def rerank_with_diagnostics(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> RerankOutcome:
        if not results:
            return RerankOutcome(())
        try:
            model = self._get_model()
            pairs = [(query, result.chunk.content) for result in results]
            scores = model.predict(pairs)
            reranked = self._convert_results(scores, results, top_k)
        except Exception as exc:
            logger.warning("Local rerank failed, returning original order: %s", exc)
            return RerankOutcome(tuple(results[:top_k]), error=str(exc))
        return RerankOutcome(tuple(reranked))

    @staticmethod
    def _convert_results(
        scores: Iterable[float], results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        from memtomem.models import SearchResult as SR

        scored = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)

        return [
            SR(chunk=r.chunk, score=float(s), rank=i + 1, source="reranked")
            for i, (s, r) in enumerate(scored[:top_k])
        ]

    async def close(self) -> None:
        self._model = None
