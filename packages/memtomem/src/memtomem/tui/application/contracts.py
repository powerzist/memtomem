"""Framework-neutral contracts for TUI application operations.

The types in this module deliberately depend only on the Python standard
library.  Domain adapters may therefore use them without importing Click,
Rich, Textual, or presentation-layer widgets.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar


_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


def _require_code(value: str, *, field_name: str) -> None:
    if not _CODE_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field_name} must start with a lowercase letter and contain only "
            "lowercase letters, digits, '.', '_', or '-'"
        )


def _require_user_text(value: str, *, field_name: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and have no surrounding whitespace")
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise ValueError(f"{field_name} must be a single user-safe line")


class OperationStatus(str, Enum):
    """Lifecycle states shared by every TUI-owned operation."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            OperationStatus.SUCCEEDED,
            OperationStatus.PARTIAL,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        }


class OperationExitPolicy(str, Enum):
    """How application shutdown treats an operation that is still active."""

    WAIT = "wait"
    CANCEL = "cancel"
    BLOCK = "block"


class MutationKind(str, Enum):
    """Observable mutation categories, independent of a domain resource type."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    REBUILT = "rebuilt"
    RESET = "reset"


@dataclass(frozen=True, slots=True)
class UserSafeWarning:
    """A stable warning that is safe to render without inspecting an exception."""

    code: str
    message: str
    recovery_action: str | None = None

    def __post_init__(self) -> None:
        _require_code(self.code, field_name="warning code")
        _require_user_text(self.message, field_name="warning message")
        if self.recovery_action is not None:
            _require_user_text(self.recovery_action, field_name="warning recovery action")


@dataclass(frozen=True, slots=True)
class UserSafeError:
    """A stable failure description that intentionally carries no exception details."""

    code: str
    message: str
    recovery_action: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        _require_code(self.code, field_name="error code")
        _require_user_text(self.message, field_name="error message")
        if self.recovery_action is not None:
            _require_user_text(self.recovery_action, field_name="error recovery action")


@dataclass(frozen=True, slots=True)
class MutationEffect:
    """A structured statement about state changed by an operation.

    ``invalidates_search_results`` is intentionally explicit.  A mutation may
    change configuration, a service, or a file without affecting search data.
    Conversely, partial or cancelled work may still have changed enough search
    data to require invalidation.
    """

    resource: str
    kind: MutationKind
    summary: str
    changed: bool = True
    affected_count: int | None = None
    invalidates_search_results: bool = False

    def __post_init__(self) -> None:
        _require_code(self.resource, field_name="mutation resource")
        _require_user_text(self.summary, field_name="mutation summary")
        if self.affected_count is not None and self.affected_count < 0:
            raise ValueError("affected_count must be non-negative")
        if not self.changed:
            if self.affected_count not in {None, 0}:
                raise ValueError("an unchanged mutation cannot have affected units")
            if self.invalidates_search_results:
                raise ValueError("an unchanged mutation cannot invalidate search results")


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """One immutable progress observation for a single operation phase."""

    phase: str
    completed: int = 0
    total: int | None = None
    skipped: int = 0
    failed: int = 0
    message: str | None = None

    def __post_init__(self) -> None:
        _require_user_text(self.phase, field_name="progress phase")
        for field_name in ("completed", "skipped", "failed"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.total is not None:
            if self.total < 0:
                raise ValueError("total must be non-negative")
            if self.processed > self.total:
                raise ValueError("completed, skipped, and failed units cannot exceed total")
        if self.message is not None:
            _require_user_text(self.message, field_name="progress message")

    @property
    def processed(self) -> int:
        return self.completed + self.skipped + self.failed

    @property
    def remaining(self) -> int | None:
        if self.total is None:
            return None
        return self.total - self.processed

    @property
    def fraction(self) -> float | None:
        if self.total is None:
            return None
        if self.total == 0:
            return 1.0
        return self.processed / self.total


ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class OperationResult(Generic[ResultT]):
    """The terminal, structured outcome of an application operation."""

    status: OperationStatus
    value: ResultT | None = None
    warnings: tuple[UserSafeWarning, ...] = ()
    effects: tuple[MutationEffect, ...] = ()
    error: UserSafeError | None = None
    recovery_action: str | None = None

    def __post_init__(self) -> None:
        if not self.status.is_terminal:
            raise ValueError("an operation result must use a terminal status")
        if self.status is OperationStatus.FAILED and self.error is None:
            raise ValueError("a failed operation result requires a user-safe error")
        if self.status in {OperationStatus.SUCCEEDED, OperationStatus.CANCELLED}:
            if self.error is not None:
                raise ValueError(f"a {self.status.value} operation result cannot carry an error")
        if self.recovery_action is not None:
            _require_user_text(self.recovery_action, field_name="operation recovery action")

    @property
    def changed(self) -> bool:
        return any(effect.changed for effect in self.effects)

    @property
    def invalidates_search_results(self) -> bool:
        return any(effect.changed and effect.invalidates_search_results for effect in self.effects)

    @classmethod
    def succeeded(
        cls,
        value: ResultT | None = None,
        *,
        warnings: tuple[UserSafeWarning, ...] = (),
        effects: tuple[MutationEffect, ...] = (),
    ) -> OperationResult[ResultT]:
        return cls(
            status=OperationStatus.SUCCEEDED,
            value=value,
            warnings=warnings,
            effects=effects,
        )

    @classmethod
    def partial(
        cls,
        value: ResultT | None = None,
        *,
        warnings: tuple[UserSafeWarning, ...] = (),
        effects: tuple[MutationEffect, ...] = (),
        error: UserSafeError | None = None,
        recovery_action: str | None = None,
    ) -> OperationResult[ResultT]:
        return cls(
            status=OperationStatus.PARTIAL,
            value=value,
            warnings=warnings,
            effects=effects,
            error=error,
            recovery_action=recovery_action,
        )

    @classmethod
    def failed(
        cls,
        error: UserSafeError,
        *,
        warnings: tuple[UserSafeWarning, ...] = (),
        effects: tuple[MutationEffect, ...] = (),
        recovery_action: str | None = None,
    ) -> OperationResult[ResultT]:
        return cls(
            status=OperationStatus.FAILED,
            warnings=warnings,
            effects=effects,
            error=error,
            recovery_action=recovery_action,
        )

    @classmethod
    def cancelled(
        cls,
        value: ResultT | None = None,
        *,
        warnings: tuple[UserSafeWarning, ...] = (),
        effects: tuple[MutationEffect, ...] = (),
        recovery_action: str | None = None,
    ) -> OperationResult[ResultT]:
        return cls(
            status=OperationStatus.CANCELLED,
            value=value,
            warnings=warnings,
            effects=effects,
            recovery_action=recovery_action,
        )


class OperationCancelled(Exception):
    """Carry a structured terminal result across a cooperative stop point."""

    def __init__(self, result: OperationResult[Any] | None = None) -> None:
        super().__init__("operation cancellation requested")
        resolved = result or OperationResult.cancelled()
        if resolved.status is not OperationStatus.CANCELLED:
            raise ValueError("OperationCancelled requires a cancelled operation result")
        self.result = resolved


class CancellationToken:
    """Read-only cancellation state passed to an operation."""

    __slots__ = ("_event",)

    def __init__(self, event: asyncio.Event) -> None:
        self._event = event

    @property
    def is_cancellation_requested(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()

    def raise_if_cancellation_requested(
        self,
        result: OperationResult[Any] | None = None,
    ) -> None:
        """Raise with optional completed effects/counts/recovery information."""

        if self.is_cancellation_requested:
            raise OperationCancelled(result)


class CancellationSource:
    """Owner of a cancellation request and the read-only token derived from it."""

    __slots__ = ("_event", "_token")

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._token = CancellationToken(self._event)

    @property
    def token(self) -> CancellationToken:
        return self._token

    def cancel(self) -> bool:
        """Request cancellation once and report whether this call changed state."""
        if self._event.is_set():
            return False
        self._event.set()
        return True


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Static execution policy and display-safe metadata for an operation."""

    name: str
    cancellable: bool = False
    conflict_keys: frozenset[str] = field(default_factory=frozenset)
    exit_policy: OperationExitPolicy = OperationExitPolicy.WAIT
    safe_parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_user_text(self.name, field_name="operation name")
        for key in self.conflict_keys:
            _require_code(key, field_name="conflict key")
        parameter_names: set[str] = set()
        for name, value in self.safe_parameters:
            _require_code(name, field_name="safe parameter name")
            _require_user_text(value, field_name="safe parameter value")
            if name in parameter_names:
                raise ValueError(f"duplicate safe parameter: {name}")
            parameter_names.add(name)
        if self.exit_policy is OperationExitPolicy.CANCEL and not self.cancellable:
            raise ValueError("a cancel-on-exit operation must be cancellable")


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    """Immutable, presentation-safe state emitted by an operation runner."""

    id: str
    name: str
    status: OperationStatus
    cancellable: bool
    exit_policy: OperationExitPolicy
    safe_parameters: tuple[tuple[str, str], ...] = ()
    progress: ProgressEvent | None = None
    warnings: tuple[UserSafeWarning, ...] = ()
    effects: tuple[MutationEffect, ...] = ()
    error: UserSafeError | None = None
    recovery_action: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return not self.status.is_terminal
