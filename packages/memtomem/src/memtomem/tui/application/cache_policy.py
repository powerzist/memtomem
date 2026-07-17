"""TUI-owned bridge from structured mutation effects to result-cache policy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol


class ResultCache(Protocol):
    """Minimal cache capability required by a persistent mutation workflow."""

    def suspend_result_cache(self) -> AbstractContextManager[None]: ...

    def invalidate_result_cache(self) -> None: ...


class MutationResult(Protocol):
    """Structured outcome surface consumed by the cache policy."""

    @property
    def invalidates_search_results(self) -> bool: ...


class MutationCacheScope:
    """Track whether the enclosing mutation changed search-visible data.

    Domain adapters should call :meth:`mark_search_results_changed` immediately
    after a confirmed write. :meth:`observe` is the normal final-result path;
    the immediate marker is the safety path for an unexpected later exception.
    """

    __slots__ = ("_search_results_changed",)

    def __init__(self) -> None:
        self._search_results_changed = False

    @property
    def search_results_changed(self) -> bool:
        return self._search_results_changed

    def mark_search_results_changed(self) -> None:
        self._search_results_changed = True

    def observe(self, result: MutationResult) -> None:
        if result.invalidates_search_results:
            self.mark_search_results_changed()


@contextmanager
def mutation_cache_scope(cache: ResultCache) -> Iterator[MutationCacheScope]:
    """Bypass cached results and invalidate once only when data changed."""

    scope = MutationCacheScope()
    with cache.suspend_result_cache():
        try:
            yield scope
        finally:
            if scope.search_results_changed:
                cache.invalidate_result_cache()


__all__ = ["MutationCacheScope", "ResultCache", "mutation_cache_scope"]
