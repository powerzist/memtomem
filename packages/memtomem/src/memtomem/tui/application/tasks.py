"""Global task ownership for work that outlives a screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class TaskSurfaceEffect(str, Enum):
    """How a shell surface transition affects domain work."""

    NONE = "none"
    PAUSE = "pause"
    CANCEL = "cancel"


class TaskExitPolicy(str, Enum):
    """What the future runtime must do when the application exits."""

    PROMPT = "prompt"
    WAIT = "wait"
    CANCEL = "cancel"
    BLOCK = "block"


class TaskCancellationPolicy(str, Enum):
    """Whether and how a task accepts cancellation."""

    NOT_SUPPORTED = "not-supported"
    COOPERATIVE_KEEP_COMPLETED = "cooperative-keep-completed"


@dataclass(frozen=True)
class TaskRecord:
    id: str
    operation: str
    status: TaskStatus = TaskStatus.QUEUED
    phase: str = "Queued"
    progress: float | None = None
    completed: int = 0
    remaining: int | None = None
    skipped: int = 0
    failed: int = 0
    warnings: tuple[str, ...] = ()
    recovery_action: str | None = None
    cancellable: bool = False
    navigation_effect: TaskSurfaceEffect = TaskSurfaceEffect.NONE
    resize_effect: TaskSurfaceEffect = TaskSurfaceEffect.NONE
    exit_policy: TaskExitPolicy = TaskExitPolicy.PROMPT
    cancellation_policy: TaskCancellationPolicy = TaskCancellationPolicy.NOT_SUPPORTED
    started_at: datetime | None = None
    ended_at: datetime | None = None
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass
class TaskCenter:
    """In-memory Phase 2 task registry; domain execution arrives in Phase 3."""

    _tasks: dict[str, TaskRecord] = field(default_factory=dict)
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def create(
        self,
        operation: str,
        *,
        parameters: dict[str, str] | None = None,
        cancellable: bool = False,
        navigation_effect: TaskSurfaceEffect = TaskSurfaceEffect.NONE,
        resize_effect: TaskSurfaceEffect = TaskSurfaceEffect.NONE,
        exit_policy: TaskExitPolicy = TaskExitPolicy.PROMPT,
        cancellation_policy: TaskCancellationPolicy | None = None,
    ) -> TaskRecord:
        if cancellation_policy is None:
            cancellation_policy = (
                TaskCancellationPolicy.COOPERATIVE_KEEP_COMPLETED
                if cancellable
                else TaskCancellationPolicy.NOT_SUPPORTED
            )
        record = TaskRecord(
            id=uuid4().hex,
            operation=operation,
            parameters=tuple((parameters or {}).items()),
            cancellable=cancellable,
            navigation_effect=navigation_effect,
            resize_effect=resize_effect,
            exit_policy=exit_policy,
            cancellation_policy=cancellation_policy,
        )
        self._tasks[record.id] = record
        self._notify()
        return record

    def update(self, task_id: str, **changes: object) -> TaskRecord:
        current = self._tasks[task_id]
        status = changes.get("status")
        if status is TaskStatus.RUNNING and current.started_at is None:
            changes["started_at"] = datetime.now(UTC)
        if status in {TaskStatus.SUCCEEDED, TaskStatus.PARTIAL, TaskStatus.FAILED}:
            changes["ended_at"] = datetime.now(UTC)
        typed_changes: Any = changes
        updated = replace(current, **typed_changes)
        self._tasks[task_id] = updated
        self._notify()
        return updated

    def get(self, task_id: str) -> TaskRecord:
        return self._tasks[task_id]

    def snapshot(self) -> tuple[TaskRecord, ...]:
        return tuple(reversed(tuple(self._tasks.values())))

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to registry changes and return an idempotent unsubscribe hook."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()
