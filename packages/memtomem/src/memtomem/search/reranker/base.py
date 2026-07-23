"""Reranker protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from memtomem.models import SearchResult


@dataclass(frozen=True, slots=True)
class RerankOutcome:
    """Per-call reranker result with non-shared degradation telemetry.

    ``rerank()`` remains the provider-facing compatibility API. The search
    pipeline uses this outcome when a provider supports it so concurrent
    searches never communicate failures through mutable provider state.
    """

    results: tuple[SearchResult, ...]
    error: str | None = None


class Reranker(Protocol):
    """Protocol for cross-encoder reranking providers."""

    async def rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        """Rerank search results using a cross-encoder model.

        Args:
            query: The search query.
            results: Candidate results from RRF fusion.
            top_k: Maximum results to return.

        Returns:
            Re-scored and re-sorted results with source="reranked".
        """
        ...

    async def close(self) -> None:
        """Release resources."""
        ...


class DiagnosticReranker(Reranker, Protocol):
    """Optional extension used by the core pipeline for degradation telemetry."""

    async def rerank_with_diagnostics(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> RerankOutcome:
        """Rerank and return a failure alongside the unchanged fallback order."""
        ...
