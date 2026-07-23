"""Reusable, literal lifecycle-state presentation for TUI operations."""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from memtomem.tui.application.contracts import OperationStatus


@dataclass(frozen=True, slots=True)
class OperationStatePresentation:
    """Structured display data for one operation lifecycle observation."""

    status: OperationStatus
    message: str
    completed: int = 0
    remaining: int | None = None
    skipped: int = 0
    failed: int = 0
    recovery: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("completed", "skipped", "failed"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.remaining is not None and self.remaining < 0:
            raise ValueError("remaining must be non-negative")


class OperationStateBlock(Vertical):
    """Render lifecycle meaning with text first and color as a secondary cue."""

    def __init__(
        self,
        presentation: OperationStatePresentation,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        semantic_classes = (
            f"operation-state state-{presentation.status.value} {classes or ''}".strip()
        )
        super().__init__(
            name=name,
            id=id,
            classes=semantic_classes,
            disabled=disabled,
        )
        self.presentation = presentation

    def compose(self) -> ComposeResult:
        yield Static(classes="operation-state-title", markup=False)
        yield Static(classes="operation-state-message", markup=False)
        yield Static(classes="operation-state-counts", markup=False)
        yield Static(classes="operation-state-recovery", markup=False)

    def on_mount(self) -> None:
        self._sync_presentation()

    def update_presentation(self, presentation: OperationStatePresentation) -> None:
        """Update one stable lifecycle block without replacing focused siblings."""
        self.presentation = presentation
        if self.is_mounted:
            self._sync_presentation()

    def _sync_presentation(self) -> None:
        state = self.presentation
        for status in OperationStatus:
            self.set_class(status is state.status, f"state-{status.value}")
        self.query_one(".operation-state-title", Static).update(f"[ {state.status.value.upper()} ]")
        self.query_one(".operation-state-message", Static).update(state.message)

        counts = self.query_one(".operation-state-counts", Static)
        has_counts = any(
            (
                state.completed,
                state.remaining is not None,
                state.skipped,
                state.failed,
            )
        )
        remaining = "?" if state.remaining is None else str(state.remaining)
        counts.update(
            " | ".join(
                (
                    f"Completed {state.completed}",
                    f"Remaining {remaining}",
                    f"Skipped {state.skipped}",
                    f"Failed {state.failed}",
                )
            )
            if has_counts
            else ""
        )
        counts.display = has_counts

        recovery = self.query_one(".operation-state-recovery", Static)
        recovery.update(state.recovery or "")
        recovery.display = state.recovery is not None


__all__ = ["OperationStateBlock", "OperationStatePresentation"]
