"""Focused lifecycle tests for the TUI-owned operation runner."""

from __future__ import annotations

import asyncio

import pytest

from memtomem.tui.application.contracts import (
    MutationEffect,
    MutationKind,
    OperationExitPolicy,
    OperationResult,
    OperationSpec,
    OperationStatus,
    ProgressEvent,
)
from memtomem.tui.application.operations import (
    OperationConflictError,
    OperationRunner,
    OperationRunnerClosedError,
    OperationShutdownBlockedError,
)


async def test_runner_owns_work_when_an_awaiting_caller_is_cancelled() -> None:
    runner = OperationRunner()
    release = asyncio.Event()

    async def operation(request: str, _context: object) -> OperationResult[str]:
        await release.wait()
        return OperationResult.succeeded(request)

    handle = runner.start(OperationSpec(name="Read"), "result", operation)
    caller = asyncio.create_task(handle.result())
    await asyncio.sleep(0)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    assert handle.snapshot.status is OperationStatus.RUNNING
    release.set()
    assert (await handle.result()).value == "result"
    await runner.shutdown()


async def test_runner_rejects_an_eager_coroutine_object() -> None:
    runner = OperationRunner()

    async def operation() -> OperationResult[None]:
        return OperationResult.succeeded()

    coroutine = operation()
    with pytest.raises(TypeError, match="callable"):
        runner.start(OperationSpec(name="Read"), None, coroutine)  # type: ignore[arg-type]
    await runner.shutdown()


async def test_cooperative_cancel_transitions_through_cancelling_to_cancelled() -> None:
    runner = OperationRunner()
    started = asyncio.Event()
    statuses: list[OperationStatus] = []
    runner.subscribe(lambda snapshot: statuses.append(snapshot.status))

    async def operation(_request: None, context: object) -> OperationResult[None]:
        started.set()
        cancellation = context.cancellation  # type: ignore[attr-defined]
        await cancellation.wait()
        cancellation.raise_if_cancellation_requested()
        raise AssertionError("unreachable")

    handle = runner.start(OperationSpec(name="Index", cancellable=True), None, operation)
    await started.wait()

    assert handle.request_cancel() is True
    assert handle.snapshot.status is OperationStatus.CANCELLING
    assert (await handle.result()).status is OperationStatus.CANCELLED
    assert statuses == [
        OperationStatus.QUEUED,
        OperationStatus.RUNNING,
        OperationStatus.CANCELLING,
        OperationStatus.CANCELLED,
    ]
    await runner.shutdown()


async def test_cooperative_cancel_preserves_completed_writes_and_resume_details() -> None:
    runner = OperationRunner()
    started = asyncio.Event()
    effect = MutationEffect(
        resource="search.index",
        kind=MutationKind.UPDATED,
        summary="One file was indexed before cancellation.",
        affected_count=1,
        invalidates_search_results=True,
    )

    async def operation(_request: None, context: object) -> OperationResult[dict[str, int]]:
        context.report_progress(  # type: ignore[attr-defined]
            ProgressEvent(phase="Indexing", completed=1, total=3)
        )
        started.set()
        cancellation = context.cancellation  # type: ignore[attr-defined]
        await cancellation.wait()
        cancellation.raise_if_cancellation_requested(
            OperationResult.cancelled(
                {"completed": 1, "remaining": 2},
                effects=(effect,),
                recovery_action="Resume the two remaining files.",
            )
        )
        raise AssertionError("unreachable")

    handle = runner.start(OperationSpec(name="Index", cancellable=True), None, operation)
    await started.wait()
    assert handle.request_cancel()

    result = await handle.result()

    assert result.status is OperationStatus.CANCELLED
    assert result.value == {"completed": 1, "remaining": 2}
    assert result.effects == (effect,)
    assert result.invalidates_search_results
    assert result.recovery_action == "Resume the two remaining files."
    assert handle.snapshot.progress == ProgressEvent(phase="Indexing", completed=1, total=3)
    assert handle.snapshot.effects == (effect,)
    assert handle.snapshot.recovery_action == "Resume the two remaining files."
    await runner.shutdown()


async def test_progress_and_partial_mutations_are_preserved_in_the_snapshot() -> None:
    runner = OperationRunner()
    effect = MutationEffect(
        resource="search.index",
        kind=MutationKind.UPDATED,
        summary="One file was indexed.",
        affected_count=1,
        invalidates_search_results=True,
    )

    async def operation(_request: None, context: object) -> OperationResult[int]:
        context.report_progress(  # type: ignore[attr-defined]
            ProgressEvent(phase="Indexing", completed=1, failed=1, total=2)
        )
        return OperationResult.partial(1, effects=(effect,))

    handle = runner.start(OperationSpec(name="Index"), None, operation)
    result = await handle.result()

    assert result.status is OperationStatus.PARTIAL
    assert result.invalidates_search_results is True
    assert handle.snapshot.status is OperationStatus.PARTIAL
    assert handle.snapshot.progress == ProgressEvent(
        phase="Indexing", completed=1, failed=1, total=2
    )
    assert handle.snapshot.effects == (effect,)
    await runner.shutdown()


async def test_conflict_keys_block_only_overlapping_active_work() -> None:
    runner = OperationRunner()
    release = asyncio.Event()

    async def blocked(_request: None, _context: object) -> OperationResult[None]:
        await release.wait()
        return OperationResult.succeeded()

    first = runner.start(
        OperationSpec(name="Index", conflict_keys=frozenset({"search.index"})),
        None,
        blocked,
    )
    await asyncio.sleep(0)

    with pytest.raises(OperationConflictError) as captured:
        runner.start(
            OperationSpec(name="Purge", conflict_keys=frozenset({"search.index"})),
            None,
            blocked,
        )
    assert captured.value.conflict_keys == frozenset({"search.index"})
    assert captured.value.conflicting_ids == (first.id,)

    unrelated = runner.start(OperationSpec(name="Status"), None, blocked)
    release.set()
    await asyncio.gather(first.result(), unrelated.result())
    await runner.shutdown()


async def test_listener_failure_is_isolated_from_operation_execution() -> None:
    runner = OperationRunner()
    observed: list[OperationStatus] = []

    def broken_listener(_snapshot: object) -> None:
        raise RuntimeError("presentation failed")

    runner.subscribe(broken_listener)
    runner.subscribe(lambda snapshot: observed.append(snapshot.status))

    async def operation(_request: None, _context: object) -> OperationResult[str]:
        return OperationResult.succeeded("done")

    handle = runner.start(OperationSpec(name="Read"), None, operation)

    assert (await handle.result()).value == "done"
    assert observed == [
        OperationStatus.QUEUED,
        OperationStatus.RUNNING,
        OperationStatus.SUCCEEDED,
    ]
    assert runner.listener_error_count == 3
    await runner.shutdown()


async def test_unexpected_exception_is_not_exposed_in_user_safe_snapshot() -> None:
    runner = OperationRunner()

    async def operation(_request: None, _context: object) -> OperationResult[None]:
        raise RuntimeError("secret-token-123")

    handle = runner.start(OperationSpec(name="Read"), None, operation)
    result = await handle.result()

    assert result.status is OperationStatus.FAILED
    assert result.error is not None
    assert result.error.code == "operation.unexpected"
    assert "secret-token-123" not in result.error.message
    assert "secret-token-123" not in repr(handle.snapshot)
    assert str(runner.debug_exception(handle.id)) == "secret-token-123"
    await runner.shutdown()


async def test_shutdown_wait_policy_drains_work_without_cancelling_it() -> None:
    runner = OperationRunner()
    release = asyncio.Event()

    async def operation(_request: None, _context: object) -> OperationResult[None]:
        await release.wait()
        return OperationResult.succeeded()

    handle = runner.start(OperationSpec(name="Read"), None, operation)
    shutdown = asyncio.create_task(runner.shutdown())
    await asyncio.sleep(0)

    assert shutdown.done() is False
    assert handle.snapshot.status is OperationStatus.RUNNING
    release.set()
    await shutdown
    assert handle.snapshot.status is OperationStatus.SUCCEEDED
    assert runner.is_closed is True
    with pytest.raises(OperationRunnerClosedError):
        runner.start(OperationSpec(name="Another read"), None, operation)


async def test_shutdown_cancel_policy_requests_cooperative_cancellation() -> None:
    runner = OperationRunner()
    started = asyncio.Event()

    async def operation(_request: None, context: object) -> OperationResult[None]:
        started.set()
        cancellation = context.cancellation  # type: ignore[attr-defined]
        await cancellation.wait()
        cancellation.raise_if_cancellation_requested()
        raise AssertionError("unreachable")

    handle = runner.start(
        OperationSpec(
            name="Index",
            cancellable=True,
            exit_policy=OperationExitPolicy.CANCEL,
        ),
        None,
        operation,
    )
    await started.wait()

    await runner.shutdown()
    assert handle.snapshot.status is OperationStatus.CANCELLED
    assert runner.is_closed is True


async def test_shutdown_block_policy_leaves_runner_open_until_work_finishes() -> None:
    runner = OperationRunner()
    release = asyncio.Event()

    async def operation(_request: None, _context: object) -> OperationResult[None]:
        await release.wait()
        return OperationResult.succeeded()

    handle = runner.start(
        OperationSpec(name="Critical migration", exit_policy=OperationExitPolicy.BLOCK),
        None,
        operation,
    )
    await asyncio.sleep(0)

    with pytest.raises(OperationShutdownBlockedError) as captured:
        await runner.shutdown()
    assert tuple(blocker.id for blocker in captured.value.blockers) == (handle.id,)
    assert runner.is_closing is False
    assert runner.is_closed is False

    release.set()
    await handle.result()
    await runner.shutdown()
    assert runner.is_closed is True


async def test_force_shutdown_cancels_blocker_only_for_external_teardown() -> None:
    runner = OperationRunner()
    started = asyncio.Event()

    async def operation(_request: None, _context: object) -> OperationResult[None]:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    handle = runner.start(
        OperationSpec(name="Critical migration", exit_policy=OperationExitPolicy.BLOCK),
        None,
        operation,
    )
    await started.wait()

    await runner.force_shutdown()

    assert runner.is_closed
    assert handle.snapshot.status is OperationStatus.CANCELLED
    assert (await handle.result()).status is OperationStatus.CANCELLED


async def test_force_shutdown_finalizes_task_cancelled_before_coroutine_entry() -> None:
    runner = OperationRunner()

    async def operation(_request: None, _context: object) -> OperationResult[None]:
        raise AssertionError("the coroutine must not start")

    handle = runner.start(
        OperationSpec(name="Queued blocker", exit_policy=OperationExitPolicy.BLOCK),
        None,
        operation,
    )

    await runner.force_shutdown()

    assert runner.is_closed
    assert handle.snapshot.status is OperationStatus.CANCELLED
    assert handle.snapshot.ended_at is not None
    assert (await handle.result()).status is OperationStatus.CANCELLED


async def test_force_shutdown_resolves_existing_waiter_with_structured_cancelled() -> None:
    runner = OperationRunner()

    async def operation(_request: None, _context: object) -> OperationResult[None]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    handle = runner.start(
        OperationSpec(name="External teardown", exit_policy=OperationExitPolicy.BLOCK),
        None,
        operation,
    )
    waiter = asyncio.create_task(handle.result())

    await runner.force_shutdown()

    assert (await waiter).status is OperationStatus.CANCELLED


async def test_terminal_history_is_bounded_while_existing_handles_remain_usable() -> None:
    runner = OperationRunner(history_limit=1)

    async def operation(request: int, _context: object) -> OperationResult[int]:
        return OperationResult.succeeded(request)

    handles = [
        runner.start(OperationSpec(name=f"Read {number}"), number, operation) for number in range(3)
    ]
    assert [await handle.result() for handle in handles]

    assert len(runner.snapshots()) == 1
    assert handles[0].snapshot.status is OperationStatus.SUCCEEDED
    assert (await handles[0].result()).value == 0
    assert handles[0].request_cancel() is False
    await runner.shutdown()
