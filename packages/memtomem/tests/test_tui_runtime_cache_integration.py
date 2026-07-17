"""RuntimeManager's standard Gate 6 mutation composition seam."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from memtomem.config import Mem2MemConfig
from memtomem.tui.application.cache_policy import MutationCacheScope
from memtomem.tui.application.contracts import (
    MutationEffect,
    MutationKind,
    OperationResult,
    OperationStatus,
)
from memtomem.tui.application.runtime import RuntimeManager
from memtomem.tui.runtime import TuiPaths


class _ResultCache:
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


@dataclass
class _Components:
    search_pipeline: _ResultCache


def _paths(tmp_path: Path) -> TuiPaths:
    root = tmp_path / ".dev" / ".memtomem"
    return TuiPaths(
        mode="dev",
        project_root=tmp_path,
        state_root=root,
        config_path=root / "config.json",
        config_d_path=root / "config.d",
        database_path=root / "memtomem.db",
        memories_path=root / "memories",
    )


def _effect() -> MutationEffect:
    return MutationEffect(
        resource="search.index",
        kind=MutationKind.UPDATED,
        summary="One indexed record changed.",
        affected_count=1,
        invalidates_search_results=True,
    )


def _manager(tmp_path: Path, cache: _ResultCache) -> RuntimeManager[_Components]:
    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> _Components:
        assert load_persisted_config is False
        return _Components(cache)

    async def closer(_components: _Components) -> None:
        return None

    return RuntimeManager(
        _paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
        environment={},
    )


@pytest.mark.parametrize("status", [OperationStatus.PARTIAL, OperationStatus.CANCELLED])
async def test_structured_changed_result_invalidates_once_before_resume(
    tmp_path: Path,
    status: OperationStatus,
) -> None:
    cache = _ResultCache()
    manager = _manager(tmp_path, cache)

    async def mutation(
        _components: _Components,
        _scope: MutationCacheScope,
    ) -> OperationResult[None]:
        assert cache.suspended
        if status is OperationStatus.PARTIAL:
            return OperationResult.partial(effects=(_effect(),))
        return OperationResult.cancelled(effects=(_effect(),))

    result = await manager.run_mutation(mutation)

    assert result.status is status
    assert cache.events == ["suspend", "invalidate", "resume"]
    await manager.close()


async def test_no_change_result_preserves_cache_generation(tmp_path: Path) -> None:
    cache = _ResultCache()
    manager = _manager(tmp_path, cache)

    async def mutation(
        _components: _Components,
        _scope: MutationCacheScope,
    ) -> OperationResult[None]:
        assert cache.suspended
        return OperationResult.succeeded()

    await manager.run_mutation(mutation)

    assert cache.events == ["suspend", "resume"]
    assert cache.invalidations == 0
    await manager.close()


async def test_write_marker_invalidates_even_when_later_code_raises(tmp_path: Path) -> None:
    cache = _ResultCache()
    manager = _manager(tmp_path, cache)

    async def mutation(
        _components: _Components,
        scope: MutationCacheScope,
    ) -> OperationResult[None]:
        scope.mark_search_results_changed()
        raise RuntimeError("after write")

    with pytest.raises(RuntimeError, match="after write"):
        await manager.run_mutation(mutation)

    assert cache.events == ["suspend", "invalidate", "resume"]
    await manager.close()


async def test_mutation_bypasses_and_invalidates_still_leased_retired_generation(
    tmp_path: Path,
) -> None:
    caches: list[_ResultCache] = []

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> _Components:
        assert load_persisted_config is False
        cache = _ResultCache()
        caches.append(cache)
        return _Components(cache)

    async def closer(_components: _Components) -> None:
        return None

    manager = RuntimeManager(
        _paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
        environment={},
    )
    retired_lease = await manager.acquire()
    await manager.swap(Mem2MemConfig())

    async def mutation(
        components: _Components,
        _scope: MutationCacheScope,
    ) -> OperationResult[None]:
        assert components.search_pipeline is caches[1]
        assert all(cache.suspended for cache in caches)
        return OperationResult.partial(effects=(_effect(),))

    await manager.run_mutation(mutation)

    assert len(caches) == 2
    for cache in caches:
        assert cache.events == ["suspend", "invalidate", "resume"]
    await retired_lease.release()
    await manager.close()
