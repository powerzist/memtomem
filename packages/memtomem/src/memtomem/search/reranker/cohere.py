"""Cohere rerank provider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from memtomem.search.reranker.base import RerankOutcome

if TYPE_CHECKING:
    from httpx import AsyncClient

    from memtomem.config import RerankConfig
    from memtomem.models import SearchResult

logger = logging.getLogger(__name__)


class CohereReranker:
    """Cross-encoder reranking via Cohere Rerank API."""

    def __init__(self, config: RerankConfig):
        self._config = config
        self._client: AsyncClient | None = None

    def _get_client(self) -> AsyncClient:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        """Rerank with the historical HTTP-only graceful fallback boundary."""
        if not results:
            return results

        documents = [result.chunk.content for result in results]
        # Client construction was outside the original fallback block. Keep
        # setup/import failures visible to direct provider callers.
        client = self._get_client()
        try:
            data = await self._request(client, query, documents, top_k)
        except Exception as exc:
            logger.warning("Cohere rerank failed, returning original order: %s", exc)
            return results[:top_k]
        # Response-to-result conversion was also outside that block, so shape
        # and score conversion failures continue to propagate directly.
        return self._convert_results(data, results, top_k)

    async def rerank_with_diagnostics(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> RerankOutcome:
        if not results:
            return RerankOutcome(())
        documents = [result.chunk.content for result in results]
        try:
            client = self._get_client()
            data = await self._request(client, query, documents, top_k)
            reranked = self._convert_results(data, results, top_k)
        except Exception as exc:
            logger.warning("Cohere rerank failed, returning original order: %s", exc)
            return RerankOutcome(tuple(results[:top_k]), error=str(exc))
        return RerankOutcome(tuple(reranked))

    async def _request(
        self,
        client: AsyncClient,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> dict[str, Any]:
        resp = await client.post(
            "https://api.cohere.ai/v1/rerank",
            json={
                "model": self._config.model,
                "query": query,
                "documents": documents,
                "top_n": min(top_k, len(documents)),
            },
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    @staticmethod
    def _convert_results(
        data: dict[str, Any],
        results: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        from memtomem.models import SearchResult as SR

        reranked = []
        for i, item in enumerate(data.get("results", [])):
            idx = item["index"]
            orig = results[idx]
            reranked.append(
                SR(
                    chunk=orig.chunk,
                    score=item["relevance_score"],
                    rank=i + 1,
                    source="reranked",
                )
            )

        return reranked[:top_k]

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
