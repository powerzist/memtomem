"""Focused tests for framework-neutral TUI application contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memtomem.tui.application.contracts import (
    CancellationSource,
    MutationEffect,
    MutationKind,
    OperationCancelled,
    OperationExitPolicy,
    OperationResult,
    OperationSpec,
    OperationStatus,
    ProgressEvent,
    UserSafeError,
    UserSafeWarning,
)


CONTRACTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "memtomem"
    / "tui"
    / "application"
    / "contracts.py"
)


def test_contract_module_has_no_presentation_or_cli_dependency() -> None:
    tree = ast.parse(CONTRACTS_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert {"click", "rich", "textual"}.isdisjoint(imported_roots)


def test_user_safe_messages_require_stable_codes_and_single_lines() -> None:
    warning = UserSafeWarning(
        code="index.partial",
        message="Some files were skipped.",
        recovery_action="Review skipped files.",
    )
    error = UserSafeError(code="index.failed", message="Indexing failed.", retryable=True)

    assert warning.code == "index.partial"
    assert error.retryable is True
    with pytest.raises(ValueError, match="warning code"):
        UserSafeWarning(code="INDEX PARTIAL", message="Unsafe code.")
    with pytest.raises(ValueError, match="single user-safe line"):
        UserSafeError(code="index.failed", message="Traceback:\nsecret-token")


def test_progress_event_derives_processed_remaining_and_fraction() -> None:
    event = ProgressEvent(phase="Indexing", completed=3, skipped=1, failed=1, total=10)

    assert event.processed == 5
    assert event.remaining == 5
    assert event.fraction == 0.5
    assert ProgressEvent(phase="Nothing to do", total=0).fraction == 1.0
    assert ProgressEvent(phase="Discovering").fraction is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"completed": -1}, "completed must be non-negative"),
        ({"total": -1}, "total must be non-negative"),
        ({"completed": 2, "skipped": 1, "total": 2}, "cannot exceed total"),
    ],
)
def test_progress_event_rejects_impossible_counts(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ProgressEvent(phase="Indexing", **kwargs)


def test_mutation_effect_makes_search_invalidation_explicit() -> None:
    changed = MutationEffect(
        resource="search.index",
        kind=MutationKind.UPDATED,
        summary="Three indexed records changed.",
        affected_count=3,
        invalidates_search_results=True,
    )
    no_op = MutationEffect(
        resource="search.index",
        kind=MutationKind.UPDATED,
        summary="No indexed records changed.",
        changed=False,
        affected_count=0,
    )

    result = OperationResult.partial(value=3, effects=(changed, no_op))
    assert result.changed is True
    assert result.invalidates_search_results is True
    with pytest.raises(ValueError, match="unchanged mutation cannot invalidate"):
        MutationEffect(
            resource="search.index",
            kind=MutationKind.UPDATED,
            summary="No indexed records changed.",
            changed=False,
            invalidates_search_results=True,
        )


def test_operation_results_allow_only_terminal_consistent_states() -> None:
    assert OperationResult.succeeded("ok").status is OperationStatus.SUCCEEDED
    assert OperationResult.partial("some").status is OperationStatus.PARTIAL
    assert OperationResult.cancelled().status is OperationStatus.CANCELLED
    with pytest.raises(ValueError, match="terminal status"):
        OperationResult(status=OperationStatus.CANCELLING)
    with pytest.raises(ValueError, match="requires a user-safe error"):
        OperationResult(status=OperationStatus.FAILED)
    with pytest.raises(ValueError, match="cannot carry an error"):
        OperationResult(
            status=OperationStatus.CANCELLED,
            error=UserSafeError(code="cancelled.error", message="Invalid cancellation."),
        )
    cancelled = OperationResult.cancelled(recovery_action="Resume from the remaining units.")
    assert cancelled.recovery_action == "Resume from the remaining units."
    with pytest.raises(ValueError, match="requires a cancelled operation result"):
        OperationCancelled(OperationResult.succeeded())


async def test_cancellation_source_exposes_a_read_only_cooperative_token() -> None:
    source = CancellationSource()
    token = source.token

    assert token.is_cancellation_requested is False
    assert source.cancel() is True
    assert source.cancel() is False
    await token.wait()
    with pytest.raises(OperationCancelled):
        token.raise_if_cancellation_requested()


def test_cancel_on_exit_requires_a_cancellable_operation() -> None:
    with pytest.raises(ValueError, match="must be cancellable"):
        OperationSpec(name="Index", exit_policy=OperationExitPolicy.CANCEL)

    spec = OperationSpec(
        name="Index",
        cancellable=True,
        exit_policy=OperationExitPolicy.CANCEL,
        conflict_keys=frozenset({"search.index"}),
        safe_parameters=(("source", "project memories"),),
    )
    assert spec.exit_policy is OperationExitPolicy.CANCEL
