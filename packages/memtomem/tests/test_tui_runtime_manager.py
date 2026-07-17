"""Phase 3 lifecycle contracts for the TUI-owned runtime manager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from memtomem.config import Mem2MemConfig
from memtomem.tui.application.runtime import (
    RuntimeManager,
    RuntimeManagerClosedError,
)
from memtomem.tui.runtime import TuiPaths


@dataclass(frozen=True)
class FakeComponents:
    name: str


def _dev_paths(tmp_path: Path) -> TuiPaths:
    state_root = tmp_path / ".dev" / ".memtomem"
    return TuiPaths(
        mode="dev",
        project_root=tmp_path,
        state_root=state_root,
        config_path=state_root / "config.json",
        config_d_path=state_root / "config.d",
        database_path=state_root / "memtomem.db",
        memories_path=state_root / "memories",
    )


async def test_construction_is_side_effect_free_and_concurrent_bootstrap_is_coalesced(
    tmp_path: Path,
) -> None:
    paths = _dev_paths(tmp_path)
    config = Mem2MemConfig()
    loaded_paths: list[TuiPaths] = []
    persisted_flags: list[bool] = []
    closed: list[FakeComponents] = []

    def load_config(received_paths: TuiPaths) -> Mem2MemConfig:
        loaded_paths.append(received_paths)
        return config

    async def factory(
        received_config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> FakeComponents:
        assert received_config is config
        persisted_flags.append(load_persisted_config)
        await asyncio.sleep(0)
        return FakeComponents("first")

    async def closer(components: FakeComponents) -> None:
        closed.append(components)

    manager = RuntimeManager[FakeComponents](
        paths,
        config_loader=load_config,
        factory=factory,
        closer=closer,
    )

    assert manager.paths is paths
    assert manager.generation == 0
    assert manager.current_generation is None
    assert not manager.started
    assert loaded_paths == []
    assert persisted_flags == []

    leases = await asyncio.gather(*(manager.acquire() for _ in range(8)))

    assert loaded_paths == [paths]
    assert persisted_flags == [False]
    assert manager.generation == 1
    assert manager.current_generation == 1
    assert manager.started
    assert {lease.generation for lease in leases} == {1}
    assert {lease.components for lease in leases} == {FakeComponents("first")}

    await asyncio.gather(*(lease.release() for lease in leases))
    assert closed == []
    await manager.close()
    assert closed == [FakeComponents("first")]


async def test_failed_candidate_keeps_the_current_generation_available(tmp_path: Path) -> None:
    paths = _dev_paths(tmp_path)
    candidate_started = asyncio.Event()
    finish_candidate = asyncio.Event()
    calls = 0
    closed: list[FakeComponents] = []

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> FakeComponents:
        nonlocal calls
        assert load_persisted_config is False
        calls += 1
        if calls == 1:
            return FakeComponents("stable")
        candidate_started.set()
        await finish_candidate.wait()
        raise LookupError("candidate failed")

    async def closer(components: FakeComponents) -> None:
        closed.append(components)

    manager = RuntimeManager[FakeComponents](
        paths,
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
    )
    await manager.bootstrap()
    stable_lease = await manager.acquire()

    reload_task = asyncio.create_task(manager.reload())
    await candidate_started.wait()

    during_reload = await manager.acquire()
    assert during_reload.generation == 1
    assert during_reload.components == FakeComponents("stable")
    await during_reload.release()

    finish_candidate.set()
    with pytest.raises(LookupError, match="candidate failed"):
        await reload_task

    assert manager.generation == 1
    assert manager.current_generation == 1
    assert closed == []
    after_failure = await manager.acquire()
    assert after_failure.generation == 1
    await after_failure.release()

    await stable_lease.release()
    await manager.close()
    assert closed == [FakeComponents("stable")]


async def test_successful_swap_retires_old_generation_after_lease_drain(
    tmp_path: Path,
) -> None:
    created = 0
    closed: list[FakeComponents] = []

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> FakeComponents:
        nonlocal created
        assert load_persisted_config is False
        created += 1
        return FakeComponents(f"generation-{created}")

    async def closer(components: FakeComponents) -> None:
        closed.append(components)

    manager = RuntimeManager[FakeComponents](
        _dev_paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
    )
    first = await manager.acquire()

    assert await manager.swap(Mem2MemConfig()) == 2
    assert manager.current_generation == 2
    assert closed == []

    second = await manager.acquire()
    assert second.generation == 2
    assert second.components == FakeComponents("generation-2")

    await first.release()
    await first.release()
    assert closed == [FakeComponents("generation-1")]

    await second.release()
    await manager.close()
    assert closed == [FakeComponents("generation-1"), FakeComponents("generation-2")]


async def test_close_waits_for_leases_and_is_concurrently_idempotent(tmp_path: Path) -> None:
    component = FakeComponents("runtime")
    closed: list[FakeComponents] = []

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> FakeComponents:
        assert load_persisted_config is False
        return component

    async def closer(components: FakeComponents) -> None:
        closed.append(components)

    manager = RuntimeManager[FakeComponents](
        _dev_paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
    )
    lease = await manager.acquire()

    first_close = asyncio.create_task(manager.close())
    second_close = asyncio.create_task(manager.close())
    for _ in range(10):
        if manager.closed:
            break
        await asyncio.sleep(0)

    assert manager.closed
    assert not first_close.done()
    assert not second_close.done()
    assert closed == []

    await lease.release()
    await asyncio.gather(first_close, second_close)
    await manager.close()

    assert manager.close_complete
    assert manager.current_generation is None
    assert closed == [component]
    with pytest.raises(RuntimeManagerClosedError, match="closed"):
        await manager.acquire()


async def test_close_errors_are_collected_without_breaking_shutdown(tmp_path: Path) -> None:
    close_error = RuntimeError("storage close failed")

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> FakeComponents:
        assert load_persisted_config is False
        return FakeComponents("runtime")

    async def closer(_components: FakeComponents) -> None:
        raise close_error

    manager = RuntimeManager[FakeComponents](
        _dev_paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
    )
    await manager.bootstrap()

    await manager.close()
    await manager.close()

    assert manager.close_complete
    assert len(manager.close_errors) == 1
    assert manager.close_errors[0].generation == 1
    assert manager.close_errors[0].error is close_error


async def test_mutation_seam_serializes_unrelated_future_use_cases(tmp_path: Path) -> None:
    manager = RuntimeManager[FakeComponents](
        _dev_paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=None,
        closer=None,
    )
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first() -> None:
        async with manager.mutation():
            order.append("first")
            first_entered.set()
            await release_first.wait()

    async def second() -> None:
        await first_entered.wait()
        async with manager.mutation():
            order.append("second")

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await first_entered.wait()
    await asyncio.sleep(0)

    assert manager.mutation_lock.locked()
    assert order == ["first"]

    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert order == ["first", "second"]

    # Closing an unused manager must not trigger config or component bootstrap.
    await manager.close()
    assert manager.generation == 0
