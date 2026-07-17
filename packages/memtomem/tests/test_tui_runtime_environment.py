"""DEV process-environment isolation for lazy runtime model loading."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest

from memtomem.config import Mem2MemConfig
from memtomem.tui.application.runtime import RuntimeManager
from memtomem.tui.runtime import TuiPaths


_CACHE_ENV = "MEMTOMEM_FASTEMBED_CACHE"


def _paths(
    tmp_path: Path,
    *,
    mode: Literal["normal", "dev"] = "dev",
) -> TuiPaths:
    root = tmp_path / (".dev/.memtomem" if mode == "dev" else ".memtomem")
    return TuiPaths(
        mode=mode,
        project_root=tmp_path if mode == "dev" else None,
        state_root=root,
        config_path=root / "config.json",
        config_d_path=root / "config.d",
        database_path=root / "memtomem.db",
        memories_path=root / "memories",
    )


async def test_dev_runtime_pins_lazy_model_cache_until_components_close(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    environment = {_CACHE_ENV: "C:/normal/cache"}
    observed_during_close: list[str | None] = []

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> object:
        assert load_persisted_config is False
        assert environment[_CACHE_ENV] == str(paths.fastembed_cache_path)
        return object()

    async def closer(_components: object) -> None:
        observed_during_close.append(environment.get(_CACHE_ENV))

    manager = RuntimeManager[object](
        paths,
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
        environment=environment,
    )

    await manager.bootstrap()
    assert environment[_CACHE_ENV] == str(paths.fastembed_cache_path)
    await manager.close()

    assert observed_during_close == [str(paths.fastembed_cache_path)]
    assert environment[_CACHE_ENV] == "C:/normal/cache"


async def test_failed_initial_dev_bootstrap_restores_missing_environment(
    tmp_path: Path,
) -> None:
    environment: dict[str, str] = {}

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> object:
        assert load_persisted_config is False
        assert _CACHE_ENV in environment
        raise RuntimeError("bootstrap failed")

    manager = RuntimeManager[object](
        _paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=None,
        environment=environment,
    )

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        await manager.bootstrap()

    assert _CACHE_ENV not in environment
    await manager.close()


async def test_normal_runtime_does_not_override_model_cache_environment(
    tmp_path: Path,
) -> None:
    environment = {_CACHE_ENV: "C:/user-selected/cache"}

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> object:
        assert load_persisted_config is False
        assert environment[_CACHE_ENV] == "C:/user-selected/cache"
        return object()

    async def closer(_components: object) -> None:
        return None

    manager = RuntimeManager[object](
        _paths(tmp_path, mode="normal"),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=closer,
        environment=environment,
    )

    await manager.bootstrap()
    await manager.close()
    assert environment[_CACHE_ENV] == "C:/user-selected/cache"


async def test_default_closer_attempts_every_resource_and_collects_failures(
    tmp_path: Path,
) -> None:
    closed: list[str] = []

    class Resource:
        def __init__(self, name: str, *, fails: bool = False) -> None:
            self.name = name
            self.fails = fails

        async def close(self) -> None:
            closed.append(self.name)
            if self.fails:
                raise RuntimeError(f"{self.name} close failed")

    components = SimpleNamespace(
        llm=Resource("llm", fails=True),
        search_pipeline=Resource("pipeline"),
        embedder=Resource("embedder", fails=True),
        storage=Resource("storage"),
    )

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> object:
        assert load_persisted_config is False
        return components

    manager = RuntimeManager[object](
        _paths(tmp_path),
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=None,
        environment={},
    )

    await manager.bootstrap()
    await manager.close()

    assert closed == ["llm", "pipeline", "embedder", "storage"]
    assert len(manager.close_errors) == 1
    grouped = manager.close_errors[0].error
    assert isinstance(grouped, ExceptionGroup)
    assert len(grouped.exceptions) == 2
