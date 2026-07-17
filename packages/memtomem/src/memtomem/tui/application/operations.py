"""Coroutine ownership and lifecycle management for TUI application work."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar, cast
from uuid import uuid4

from memtomem.tui.application.contracts import (
    CancellationSource,
    CancellationToken,
    OperationCancelled,
    OperationExitPolicy,
    OperationResult,
    OperationSnapshot,
    OperationSpec,
    OperationStatus,
    ProgressEvent,
    UserSafeError,
)


RequestT = TypeVar("RequestT")
ResultT = TypeVar("ResultT")
OperationCallable = Callable[[RequestT, "OperationContext"], Awaitable[OperationResult[ResultT]]]
OperationListener = Callable[[OperationSnapshot], None]


class OperationConflictError(RuntimeError):
    """Raised before start when an operation overlaps an active mutation."""

    def __init__(self, conflict_keys: frozenset[str], conflicting_ids: tuple[str, ...]) -> None:
        self.conflict_keys = conflict_keys
        self.conflicting_ids = conflicting_ids
        keys = ", ".join(sorted(conflict_keys))
        super().__init__(f"operation conflicts with active work on: {keys}")


class OperationRunnerClosedError(RuntimeError):
    """Raised when new work is submitted after shutdown starts."""


class OperationShutdownBlockedError(RuntimeError):
    """Raised when a block-on-exit operation prevents orderly shutdown."""

    def __init__(self, blockers: tuple[OperationSnapshot, ...]) -> None:
        self.blockers = blockers
        names = ", ".join(blocker.name for blocker in blockers)
        super().__init__(f"application shutdown is blocked by active work: {names}")


class OperationContext:
    """Capabilities made available to a running application operation."""

    __slots__ = ("_cancellation", "_report_progress")

    def __init__(
        self,
        cancellation: CancellationToken,
        report_progress: Callable[[ProgressEvent], None],
    ) -> None:
        self._cancellation = cancellation
        self._report_progress = report_progress

    @property
    def cancellation(self) -> CancellationToken:
        return self._cancellation

    def report_progress(self, event: ProgressEvent) -> None:
        self._report_progress(event)


@dataclass(slots=True)
class _OperationEntry:
    spec: OperationSpec
    source: CancellationSource
    snapshot: OperationSnapshot
    task: asyncio.Task[OperationResult[Any]] | None = None
    result: OperationResult[Any] | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    debug_exception: BaseException | None = None


class OperationHandle(Generic[ResultT]):
    """A stable reference to runner-owned work.

    Cancelling a caller that awaits :meth:`result` does not cancel the domain
    operation.  Cancellation must go through :meth:`request_cancel` so the
    operation can preserve completed units and return a structured result.
    """

    __slots__ = ("_entry", "_id", "_runner")

    def __init__(
        self,
        runner: OperationRunner,
        operation_id: str,
        entry: _OperationEntry,
    ) -> None:
        self._runner = runner
        self._id = operation_id
        self._entry = entry

    @property
    def id(self) -> str:
        return self._id

    @property
    def snapshot(self) -> OperationSnapshot:
        return self._entry.snapshot

    def request_cancel(self) -> bool:
        return self._runner._request_cancel_entry(self._entry)

    async def result(self) -> OperationResult[ResultT]:
        result = await self._runner._wait_entry(self._entry)
        return cast(OperationResult[ResultT], result)


class OperationRunner:
    """Own and coordinate application operation coroutines.

    The runner accepts a callable that creates the awaitable inside a
    runner-owned ``asyncio.Task``.  It never accepts an eagerly-created
    coroutine as the unit of work, preventing caller cancellation or screen
    unmounting from accidentally owning the domain operation.
    """

    def __init__(self, *, history_limit: int = 100) -> None:
        if history_limit < 0:
            raise ValueError("history_limit must be non-negative")
        self._entries: dict[str, _OperationEntry] = {}
        self._listeners: list[OperationListener] = []
        self._listener_error_count = 0
        self._closing = False
        self._closed = False
        self._history_limit = history_limit

    @property
    def is_closing(self) -> bool:
        return self._closing

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def listener_error_count(self) -> int:
        return self._listener_error_count

    def start(
        self,
        spec: OperationSpec,
        request: RequestT,
        operation: OperationCallable[RequestT, ResultT],
    ) -> OperationHandle[ResultT]:
        if self._closing or self._closed:
            raise OperationRunnerClosedError("the operation runner is shutting down")
        if not callable(operation):
            if inspect.iscoroutine(operation):
                operation.close()
            raise TypeError("operation must be a callable that creates an awaitable")

        conflict_keys, conflicting_ids = self._find_conflicts(spec.conflict_keys)
        if conflict_keys:
            raise OperationConflictError(conflict_keys, conflicting_ids)

        operation_id = uuid4().hex
        snapshot = OperationSnapshot(
            id=operation_id,
            name=spec.name,
            status=OperationStatus.QUEUED,
            cancellable=spec.cancellable,
            exit_policy=spec.exit_policy,
            safe_parameters=spec.safe_parameters,
        )
        entry = _OperationEntry(
            spec=spec,
            source=CancellationSource(),
            snapshot=snapshot,
        )
        self._entries[operation_id] = entry
        self._notify(snapshot)
        task = asyncio.create_task(
            self._execute(entry, request, operation),
            name=f"memtomem-tui:{spec.name}:{operation_id}",
        )
        entry.task = cast(asyncio.Task[OperationResult[Any]], task)
        return OperationHandle(self, operation_id, entry)

    def snapshot(self, operation_id: str) -> OperationSnapshot:
        return self._entries[operation_id].snapshot

    def snapshots(self) -> tuple[OperationSnapshot, ...]:
        return tuple(entry.snapshot for entry in self._entries.values())

    def active_snapshots(self) -> tuple[OperationSnapshot, ...]:
        return tuple(snapshot for snapshot in self.snapshots() if snapshot.is_active)

    def subscribe(self, listener: OperationListener) -> Callable[[], None]:
        """Subscribe a synchronous listener and return an idempotent unsubscribe hook."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def request_cancel(self, operation_id: str) -> bool:
        entry = self._entries.get(operation_id)
        if entry is None:
            return False
        return self._request_cancel_entry(entry)

    def _request_cancel_entry(self, entry: _OperationEntry) -> bool:
        if not entry.spec.cancellable or entry.snapshot.status.is_terminal:
            return False
        if not entry.source.cancel():
            return False
        entry.snapshot = replace(entry.snapshot, status=OperationStatus.CANCELLING)
        self._notify(entry.snapshot)
        return True

    async def wait(self, operation_id: str) -> OperationResult[Any]:
        return await self._wait_entry(self._entries[operation_id])

    async def _wait_entry(self, entry: _OperationEntry) -> OperationResult[Any]:
        if entry.result is None:
            await entry.finished.wait()
        if entry.result is None:  # pragma: no cover - _finish sets both atomically
            raise RuntimeError("operation finished without a structured result")
        return entry.result

    async def shutdown(self) -> None:
        """Apply per-operation WAIT/CANCEL/BLOCK policies and stop accepting work."""
        if self._closed:
            return

        active_entries = [entry for entry in self._entries.values() if entry.snapshot.is_active]
        blockers = tuple(
            entry.snapshot
            for entry in active_entries
            if entry.spec.exit_policy is OperationExitPolicy.BLOCK
        )
        if blockers:
            raise OperationShutdownBlockedError(blockers)

        self._closing = True
        for entry in active_entries:
            if entry.spec.exit_policy is OperationExitPolicy.CANCEL:
                self.request_cancel(entry.snapshot.id)

        tasks = [entry.task for entry in active_entries if entry.task is not None]
        if tasks:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tasks),
                return_exceptions=True,
            )
        self._closed = True

    async def force_shutdown(self) -> None:
        """Cancel runner tasks during external teardown, ignoring BLOCK policy.

        Normal user-requested exit must use :meth:`shutdown`; this method is
        reserved for an app/driver unmount that can no longer keep the TUI
        alive to honor a blocker.
        """

        if self._closed:
            return
        self._closing = True
        active_entries = [entry for entry in self._entries.values() if entry.snapshot.is_active]
        for entry in active_entries:
            entry.source.cancel()
            task = entry.task
            if task is not None and not task.done():
                task.cancel()
        tasks = [entry.task for entry in active_entries if entry.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for entry in active_entries:
            if entry.snapshot.is_active:
                self._finish(entry, OperationResult.cancelled())
        self._closed = True

    def debug_exception(self, operation_id: str) -> BaseException | None:
        """Return an internal exception for logging; snapshots never expose it."""
        return self._entries[operation_id].debug_exception

    def _find_conflicts(
        self, requested_keys: frozenset[str]
    ) -> tuple[frozenset[str], tuple[str, ...]]:
        if not requested_keys:
            return frozenset(), ()
        conflicts: set[str] = set()
        conflicting_ids: list[str] = []
        for entry in self._entries.values():
            if not entry.snapshot.is_active:
                continue
            overlap = requested_keys & entry.spec.conflict_keys
            if overlap:
                conflicts.update(overlap)
                conflicting_ids.append(entry.snapshot.id)
        return frozenset(conflicts), tuple(conflicting_ids)

    async def _execute(
        self,
        entry: _OperationEntry,
        request: RequestT,
        operation: OperationCallable[RequestT, ResultT],
    ) -> OperationResult[ResultT]:
        if entry.source.token.is_cancellation_requested:
            result: OperationResult[ResultT] = OperationResult.cancelled()
            self._finish(entry, result)
            return result

        entry.snapshot = replace(
            entry.snapshot,
            status=OperationStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self._notify(entry.snapshot)
        context = OperationContext(
            entry.source.token,
            lambda event: self._set_progress(entry, event),
        )

        try:
            result = await operation(request, context)
            if not isinstance(result, OperationResult):
                raise TypeError("operation callable did not return OperationResult")
        except OperationCancelled as cancellation:
            result = cast(OperationResult[ResultT], cancellation.result)
        except asyncio.CancelledError:
            entry.source.cancel()
            result = OperationResult.cancelled()
        except Exception as error:
            entry.debug_exception = error
            result = OperationResult.failed(
                UserSafeError(
                    code="operation.unexpected",
                    message="The operation could not be completed.",
                    recovery_action="Review the operation details and try again.",
                    retryable=True,
                )
            )

        self._finish(entry, result)
        return result

    def _set_progress(self, entry: _OperationEntry, event: ProgressEvent) -> None:
        if entry.snapshot.status.is_terminal:
            return
        entry.snapshot = replace(entry.snapshot, progress=event)
        self._notify(entry.snapshot)

    def _finish(self, entry: _OperationEntry, result: OperationResult[Any]) -> None:
        entry.result = result
        entry.snapshot = replace(
            entry.snapshot,
            status=result.status,
            warnings=result.warnings,
            effects=result.effects,
            error=result.error,
            recovery_action=result.recovery_action,
            ended_at=datetime.now(UTC),
        )
        entry.finished.set()
        self._notify(entry.snapshot)
        self._prune_history()

    def _prune_history(self) -> None:
        terminal_ids = [
            operation_id
            for operation_id, entry in self._entries.items()
            if entry.snapshot.status.is_terminal
        ]
        excess = max(0, len(terminal_ids) - self._history_limit)
        for operation_id in terminal_ids[:excess]:
            self._entries.pop(operation_id, None)

    def _notify(self, snapshot: OperationSnapshot) -> None:
        for listener in tuple(self._listeners):
            try:
                listener(snapshot)
            except Exception:
                self._listener_error_count += 1
