"""Gate 6 tests for translating mutation effects into cache lifecycle."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from memtomem.tui.application.cache_policy import mutation_cache_scope
from memtomem.tui.application.contracts import (
    MutationEffect,
    MutationKind,
    OperationResult,
)


class _CacheProbe:
    def __init__(self) -> None:
        self.suspended = False
        self.invalidations = 0
        self.events: list[str] = []

    @contextmanager
    def suspend_result_cache(self):
        self.suspended = True
        self.events.append("suspend")
        try:
            yield
        finally:
            self.events.append("resume")
            self.suspended = False

    def invalidate_result_cache(self) -> None:
        assert self.suspended
        self.events.append("invalidate")
        self.invalidations += 1


def _changed_effect() -> MutationEffect:
    return MutationEffect(
        resource="search.index",
        kind=MutationKind.UPDATED,
        summary="One search-visible record changed.",
        affected_count=1,
        invalidates_search_results=True,
    )


def test_no_change_result_resumes_without_invalidation() -> None:
    cache = _CacheProbe()

    with mutation_cache_scope(cache) as scope:
        assert cache.suspended
        scope.observe(OperationResult.succeeded())

    assert cache.events == ["suspend", "resume"]
    assert cache.invalidations == 0


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_partial_or_cancelled_write_invalidates_before_cache_resumes(status: str) -> None:
    cache = _CacheProbe()
    effect = _changed_effect()

    with mutation_cache_scope(cache) as scope:
        result = getattr(OperationResult, status)(effects=(effect,))
        scope.observe(result)

    assert cache.events == ["suspend", "invalidate", "resume"]
    assert cache.invalidations == 1


def test_confirmed_write_still_invalidates_when_later_code_raises() -> None:
    cache = _CacheProbe()

    with pytest.raises(RuntimeError, match="after write"):
        with mutation_cache_scope(cache) as scope:
            scope.mark_search_results_changed()
            raise RuntimeError("after write")

    assert cache.events == ["suspend", "invalidate", "resume"]
    assert cache.invalidations == 1
