"""Generation-safe ownership of the long-lived TUI runtime.

Constructing :class:`RuntimeManager` is deliberately side-effect free.  A
runtime is opened only when a feature explicitly asks for a lease, so Home and
Status can continue to use their read-only diagnostic paths without creating
or migrating storage.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar, cast

from memtomem.tui.application.cache_policy import (
    MutationCacheScope,
    ResultCache,
    mutation_cache_scope,
)
from memtomem.tui.application.contracts import OperationResult
from memtomem.tui.runtime import TuiPaths, load_tui_config

if TYPE_CHECKING:
    from memtomem.config import Mem2MemConfig
    from memtomem.server.component_factory import Components


ComponentT = TypeVar("ComponentT")
MutationResultT = TypeVar("MutationResultT")
ComponentFactory = Callable[..., Awaitable[ComponentT]]
ComponentCloser = Callable[[ComponentT], Awaitable[None]]
ConfigLoader = Callable[[TuiPaths], "Mem2MemConfig"]
_FASTEMBED_CACHE_ENV = "MEMTOMEM_FASTEMBED_CACHE"
_ENV_MISSING = object()


class _ResultCacheGroup:
    """Apply one mutation cache policy to every still-leased generation."""

    def __init__(self, caches: tuple[ResultCache, ...]) -> None:
        self._caches = caches

    @contextmanager
    def suspend_result_cache(self):
        with ExitStack() as stack:
            for cache in self._caches:
                stack.enter_context(cache.suspend_result_cache())
            yield

    def invalidate_result_cache(self) -> None:
        for cache in self._caches:
            cache.invalidate_result_cache()


class RuntimeManagerClosedError(RuntimeError):
    """Raised when work is requested after application shutdown has begun."""


@dataclass(frozen=True, slots=True)
class RuntimeCloseError:
    """A component shutdown error retained for the application error surface."""

    generation: int
    error: Exception


@dataclass(slots=True)
class _RuntimeGeneration(Generic[ComponentT]):
    number: int
    components: ComponentT
    leases: int = 0
    retired: bool = False
    close_task: asyncio.Task[None] | None = None
    closed: bool = False
    closed_event: asyncio.Event = field(default_factory=asyncio.Event)


class RuntimeLease(Generic[ComponentT]):
    """Keep one runtime generation alive while a use case is using it.

    Leases are idempotently releasable and may be used directly as async
    context managers.  A caller should not retain ``components`` after the
    lease has been released.
    """

    __slots__ = ("_generation", "_manager", "_released")

    def __init__(
        self,
        manager: RuntimeManager[ComponentT],
        generation: _RuntimeGeneration[ComponentT],
    ) -> None:
        self._manager = manager
        self._generation = generation
        self._released = False

    @property
    def generation(self) -> int:
        return self._generation.number

    @property
    def components(self) -> ComponentT:
        return self._generation.components

    @property
    def released(self) -> bool:
        return self._released

    async def release(self) -> None:
        """Release this lease once; repeated calls are harmless."""
        if self._released:
            return
        self._released = True
        await self._manager._release(self._generation)

    async def __aenter__(self) -> RuntimeLease[ComponentT]:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.release()


async def _default_factory(
    config: Mem2MemConfig,
    *,
    load_persisted_config: bool,
) -> Components:
    from memtomem.server.component_factory import create_components

    return await create_components(
        config,
        load_persisted_config=load_persisted_config,
    )


async def _default_closer(components: Components) -> None:
    """Attempt every component close even when an earlier resource fails."""

    resources = (
        ("llm", components.llm),
        ("search pipeline", components.search_pipeline),
        ("embedder", components.embedder),
        ("storage", components.storage),
    )
    errors: list[Exception] = []
    for label, resource in resources:
        if resource is None:
            continue
        try:
            await resource.close()
        except Exception as exc:
            exc.add_note(f"TUI runtime resource close failed: {label}")
            errors.append(exc)
    if errors:
        raise ExceptionGroup("one or more TUI runtime resources failed to close", errors)


class RuntimeManager(Generic[ComponentT]):
    """Own lazy component bootstrap and atomic runtime-generation swaps.

    Candidate construction is serialized while the current generation remains
    available to readers.  A successful candidate is installed atomically;
    the replaced generation is closed only after its outstanding leases drain.
    Candidate creation failure leaves the current generation untouched.
    """

    def __init__(
        self,
        paths: TuiPaths,
        *,
        config_loader: ConfigLoader = load_tui_config,
        factory: ComponentFactory[ComponentT] | None = None,
        closer: ComponentCloser[ComponentT] | None = None,
        environment: MutableMapping[str, str] | None = None,
        result_cache_getter: Callable[[ComponentT], ResultCache] | None = None,
    ) -> None:
        self.paths = paths
        self._config_loader = config_loader
        self._factory = factory or cast(ComponentFactory[ComponentT], _default_factory)
        self._closer = closer or cast(ComponentCloser[ComponentT], _default_closer)
        self._environment = os.environ if environment is None else environment
        self._environment_active = False
        self._previous_fastembed_cache: str | object = _ENV_MISSING
        self._result_cache_getter = result_cache_getter or self._default_result_cache

        self._state_lock = asyncio.Lock()
        self._swap_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._mutation_lock = asyncio.Lock()
        self._close_complete = asyncio.Event()

        self._current: _RuntimeGeneration[ComponentT] | None = None
        self._generations: dict[int, _RuntimeGeneration[ComponentT]] = {}
        self._last_generation = 0
        self._closed = False
        self._close_errors: list[RuntimeCloseError] = []

    @property
    def generation(self) -> int:
        """Return the last successfully installed generation, or zero."""
        return self._last_generation

    @property
    def current_generation(self) -> int | None:
        """Return the currently leasable generation."""
        current = self._current
        return current.number if current is not None else None

    @property
    def started(self) -> bool:
        """Return whether an active runtime has been lazily bootstrapped."""
        return self._current is not None

    @property
    def closed(self) -> bool:
        """Return whether application shutdown has begun."""
        return self._closed

    @property
    def close_complete(self) -> bool:
        """Return whether every runtime generation has finished closing."""
        return self._close_complete.is_set()

    @property
    def close_errors(self) -> tuple[RuntimeCloseError, ...]:
        """Return component close failures collected across all generations."""
        return tuple(self._close_errors)

    @property
    def mutation_lock(self) -> asyncio.Lock:
        """One manager-wide seam for serializing future mutation use cases."""
        return self._mutation_lock

    @asynccontextmanager
    async def mutation(self) -> AsyncIterator[None]:
        """Low-level serialization seam for mutations with no search data effect."""
        async with self._mutation_lock:
            yield

    async def run_mutation(
        self,
        operation: Callable[
            [ComponentT, MutationCacheScope],
            Awaitable[OperationResult[MutationResultT]],
        ],
    ) -> OperationResult[MutationResultT]:
        """Run a search-visible mutation through the complete Gate 6 policy.

        The operation receives the leased components and a cache scope. It
        should mark the scope immediately after a confirmed write; the final
        structured result is also observed automatically. Cache invalidation,
        when required, occurs once before the bypass window closes.
        """

        if not callable(operation):
            raise TypeError("mutation operation must be a callable")
        async with self._mutation_lock:
            async with self.lease() as lease:
                cache_leases = await self._acquire_live_cache_leases()
                try:
                    caches = self._result_caches(cache_leases)
                    with mutation_cache_scope(_ResultCacheGroup(caches)) as cache_scope:
                        result = await operation(lease.components, cache_scope)
                        if not isinstance(result, OperationResult):
                            raise TypeError("mutation operation did not return OperationResult")
                        cache_scope.observe(result)
                        return result
                finally:
                    await asyncio.gather(*(cache_lease.release() for cache_lease in cache_leases))

    async def bootstrap(self) -> int:
        """Lazily create the first generation, coalescing concurrent callers."""
        async with self._state_lock:
            self._require_open()
            if self._current is not None:
                return self._current.number

        async with self._swap_lock:
            async with self._state_lock:
                self._require_open()
                if self._current is not None:
                    return self._current.number
            return await self._create_and_swap(None)

    async def acquire(self) -> RuntimeLease[ComponentT]:
        """Acquire a lease on the current runtime, bootstrapping if necessary."""
        await self.bootstrap()
        async with self._state_lock:
            self._require_open()
            current = self._current
            if current is None:  # Defensive: swaps never leave an open gap.
                raise RuntimeError("runtime bootstrap completed without an active generation")
            current.leases += 1
            return RuntimeLease(self, current)

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[RuntimeLease[ComponentT]]:
        """Acquire and reliably release a runtime lease."""
        lease = await self.acquire()
        try:
            yield lease
        finally:
            await lease.release()

    async def reload(self, config: Mem2MemConfig | None = None) -> int:
        """Build and atomically install a fresh runtime generation.

        Passing an already validated config is a seam for future config use
        cases.  This method itself does not persist config or implement the
        unresolved configuration side-effect decision gates.
        """
        async with self._mutation_lock:
            async with self._swap_lock:
                async with self._state_lock:
                    self._require_open()
                return await self._create_and_swap(config)

    async def swap(self, config: Mem2MemConfig | None = None) -> int:
        """Alias ``reload`` for callers that describe the operation as a swap."""
        return await self.reload(config)

    async def close(self) -> None:
        """Retire every generation and wait for outstanding leases to drain.

        Component close failures are retained in :attr:`close_errors` instead
        of preventing the remaining generations from closing.  Repeated and
        concurrent calls are idempotent.
        """
        async with self._close_lock:
            if self._close_complete.is_set():
                return

            async with self._swap_lock:
                async with self._state_lock:
                    self._closed = True
                    self._current = None
                    generations = tuple(self._generations.values())
                    for generation in generations:
                        generation.retired = True

            await asyncio.gather(*(self._close_if_idle(generation) for generation in generations))
            await asyncio.gather(*(generation.closed_event.wait() for generation in generations))
            self._restore_dev_environment()
            self._close_complete.set()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeManagerClosedError("runtime manager is closed")

    @staticmethod
    def _default_result_cache(components: ComponentT) -> ResultCache:
        cache = getattr(components, "search_pipeline", None)
        if cache is None:
            raise TypeError("runtime components do not expose a search_pipeline cache")
        if not callable(getattr(cache, "suspend_result_cache", None)) or not callable(
            getattr(cache, "invalidate_result_cache", None)
        ):
            raise TypeError("runtime search_pipeline does not support the result-cache policy")
        return cast(ResultCache, cache)

    async def _acquire_live_cache_leases(self) -> tuple[RuntimeLease[ComponentT], ...]:
        """Keep current and still-used retired generations alive during mutation."""

        async with self._state_lock:
            generations = tuple(
                generation
                for generation in self._generations.values()
                if not generation.closed and (generation is self._current or generation.leases > 0)
            )
            for generation in generations:
                generation.leases += 1
            return tuple(RuntimeLease(self, generation) for generation in generations)

    def _result_caches(
        self,
        leases: tuple[RuntimeLease[ComponentT], ...],
    ) -> tuple[ResultCache, ...]:
        caches: list[ResultCache] = []
        seen: set[int] = set()
        for lease in leases:
            cache = self._result_cache_getter(lease.components)
            identity = id(cache)
            if identity not in seen:
                seen.add(identity)
                caches.append(cache)
        if not caches:
            raise RuntimeError("mutation requires at least one live result cache")
        return tuple(caches)

    async def _create_and_swap(self, config: Mem2MemConfig | None) -> int:
        activated_here = self._activate_dev_environment()
        candidate: ComponentT | None = None
        number = self._last_generation + 1
        try:
            resolved_config = config if config is not None else self._config_loader(self.paths)
            candidate = await self._factory(
                resolved_config,
                load_persisted_config=False,
            )
            generation = _RuntimeGeneration(number=number, components=candidate)
            async with self._state_lock:
                self._require_open()
                previous = self._current
                self._current = generation
                self._last_generation = number
                self._generations[number] = generation
                if previous is not None:
                    previous.retired = True
        except BaseException:
            if candidate is not None:
                await self._close_uninstalled(number, candidate)
            if activated_here and self._current is None:
                self._restore_dev_environment()
            raise

        if previous is not None:
            await self._close_if_idle(previous)
        return number

    def _activate_dev_environment(self) -> bool:
        """Pin lazy FastEmbed loads to the dev state tree for runtime lifetime."""

        if not self.paths.is_dev or self._environment_active:
            return False
        self._previous_fastembed_cache = self._environment.get(
            _FASTEMBED_CACHE_ENV,
            _ENV_MISSING,
        )
        self._environment[_FASTEMBED_CACHE_ENV] = str(self.paths.fastembed_cache_path)
        self._environment_active = True
        return True

    def _restore_dev_environment(self) -> None:
        if not self._environment_active:
            return
        if self._previous_fastembed_cache is _ENV_MISSING:
            self._environment.pop(_FASTEMBED_CACHE_ENV, None)
        else:
            self._environment[_FASTEMBED_CACHE_ENV] = cast(
                str,
                self._previous_fastembed_cache,
            )
        self._previous_fastembed_cache = _ENV_MISSING
        self._environment_active = False

    async def _release(self, generation: _RuntimeGeneration[ComponentT]) -> None:
        async with self._state_lock:
            if generation.leases <= 0:
                raise RuntimeError("runtime generation lease count underflow")
            generation.leases -= 1
            should_close = generation.retired and generation.leases == 0
        if should_close:
            await self._close_if_idle(generation)

    async def _close_if_idle(self, generation: _RuntimeGeneration[ComponentT]) -> None:
        async with self._state_lock:
            if not generation.retired or generation.leases != 0 or generation.closed:
                return
            if generation.close_task is None:
                generation.close_task = asyncio.create_task(
                    self._finish_close(generation),
                    name=f"memtomem-tui-runtime-close-{generation.number}",
                )
            close_task = generation.close_task
        await asyncio.shield(close_task)

    async def _finish_close(self, generation: _RuntimeGeneration[ComponentT]) -> None:
        try:
            await self._closer(generation.components)
        except Exception as exc:
            async with self._state_lock:
                self._close_errors.append(
                    RuntimeCloseError(generation=generation.number, error=exc)
                )
        finally:
            async with self._state_lock:
                generation.closed = True
                generation.closed_event.set()

    async def _close_uninstalled(self, number: int, components: ComponentT) -> None:
        try:
            await self._closer(components)
        except Exception as exc:
            async with self._state_lock:
                self._close_errors.append(RuntimeCloseError(generation=number, error=exc))


__all__ = [
    "RuntimeCloseError",
    "RuntimeLease",
    "RuntimeManager",
    "RuntimeManagerClosedError",
]
