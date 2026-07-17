"""Rendered lifecycle-state contract for the reusable TUI status block."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from memtomem.tui.application.contracts import OperationStatus
from memtomem.tui.styles import load_tui_css
from memtomem.tui.widgets.operation_status import (
    OperationStateBlock,
    OperationStatePresentation,
)


class _StateApp(App[None]):
    CSS = load_tui_css()

    def compose(self) -> ComposeResult:
        for status in OperationStatus:
            yield OperationStateBlock(
                OperationStatePresentation(
                    status=status,
                    message=f"Literal [{status.value}] state.",
                    completed=2,
                    remaining=3,
                    skipped=1,
                    failed=1,
                    recovery="Resume from the remaining units.",
                )
            )


async def test_all_operation_states_render_distinct_literal_labels_and_counts() -> None:
    app = _StateApp()

    async with app.run_test(size=(80, 30)):
        blocks = list(app.query(OperationStateBlock))
        assert len(blocks) == len(OperationStatus)
        for status, block in zip(OperationStatus, blocks, strict=True):
            rendered = "\n".join(str(item.render()) for item in block.query(Static))
            assert f"[ {status.value.upper()} ]" in rendered
            assert f"Literal [{status.value}] state." in rendered
            assert "Completed 2 | Remaining 3 | Skipped 1 | Failed 1" in rendered
            assert block.has_class(f"state-{status.value}")


@pytest.mark.parametrize("field", ["completed", "remaining", "skipped", "failed"])
def test_operation_state_counts_cannot_be_negative(field: str) -> None:
    with pytest.raises(ValueError, match="must be non-negative"):
        OperationStatePresentation(
            status=OperationStatus.FAILED,
            message="Invalid counts.",
            **{field: -1},
        )
