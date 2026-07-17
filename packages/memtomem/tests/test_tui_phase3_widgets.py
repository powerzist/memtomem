"""Phase 3 tests for reusable, domain-neutral Textual presenters."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.coordinate import Coordinate
from textual.widgets import Static

from memtomem.tui.styles import load_tui_css
from memtomem.tui.terminal import BorderStyle
from memtomem.tui.widgets.controls import ModalButton, PanelButton, TuiInput
from memtomem.tui.widgets.forms import ActionBar, FormRow
from memtomem.tui.widgets.preview import (
    ConfirmationBlock,
    EmptyState,
    ErrorState,
    PreviewBlock,
    PreviewConfirmScreen,
    PreviewItem,
    PreviewPresentation,
)
from memtomem.tui.widgets.tables import (
    SemanticDataTable,
    TableColumn,
    TableRow,
    TableView,
)


def _rendered_text(root: object) -> str:
    return "\n".join(str(widget.render()) for widget in root.query(Static))


def _composited_text(app: App[object]) -> str:
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


class _ComponentApp(App[None]):
    CSS = load_tui_css()

    def compose(self) -> ComposeResult:
        yield FormRow(
            "Source [literal]",
            TuiInput(value="C:/memory/[draft].md", classes="text-input"),
            supporting_text="Keep [brackets] literal",
            error="Example [bold] error",
        )
        yield ActionBar(PanelButton("Run", classes="action-button cyan"))
        yield PreviewBlock(
            PreviewPresentation(
                title="CHANGE [ONE]",
                summary="Review [not markup] before applying.",
                fingerprint="stable-1",
                items=(PreviewItem("Path", "C:/memory/[draft].md"),),
            )
        )
        yield ErrorState("E[1]", "Visible [safe] message", recovery="Retry [later]")


class _TableApp(App[None]):
    CSS = load_tui_css()

    def compose(self) -> ComposeResult:
        columns = (
            TableColumn("name", "NAME"),
            TableColumn("path", "PATH"),
        )
        yield TableView(
            columns,
            (TableRow(("alpha[1]", "C:/memory/[alpha].md"), key="alpha"),),
            id="populated-table-view",
        )
        yield TableView(
            columns,
            empty_title="NO MATCHES",
            empty_message="No rows matched [literal].",
            id="empty-table-view",
        )


class _ModalHostApp(App[bool | None]):
    CSS = load_tui_css()

    def __init__(self, modal: PreviewConfirmScreen) -> None:
        super().__init__()
        self.modal = modal
        self.decision: bool | None = None

    def compose(self) -> ComposeResult:
        yield PanelButton("Open preview", id="modal-opener")

    def on_mount(self) -> None:
        self.query_one("#modal-opener", PanelButton).focus()
        self.push_screen(self.modal, self._capture_decision)

    def _capture_decision(self, decision: bool) -> None:
        self.decision = decision


def _preview(*, fingerprint: str = "state[1]") -> PreviewPresentation:
    return PreviewPresentation(
        title="DELETE [SAFE]",
        summary="One caller-supplied change will be applied.",
        fingerprint=fingerprint,
        items=(
            PreviewItem("Target", "C:/memory/[safe].md"),
            PreviewItem("Effect", "Caller supplied", tone="warning"),
        ),
    )


async def test_form_preview_error_and_action_families_render_literal_text() -> None:
    app = _ComponentApp()
    async with app.run_test(size=(80, 30)):
        row = app.query_one(FormRow)
        assert row.has_class("form-row")
        assert row.query_one(TuiInput).value == "C:/memory/[draft].md"

        action_bar = app.query_one(ActionBar)
        assert action_bar.has_class("action-bar")
        assert isinstance(action_bar.query_one(PanelButton), PanelButton)

        preview = app.query_one(PreviewBlock)
        assert preview.has_class("preview-block")
        error = app.query_one(ErrorState)
        assert error.has_class("error-state")

        rendered = _rendered_text(app.screen)
        assert "Source [literal]" in rendered
        assert "Keep [brackets] literal" in rendered
        assert "Example [bold] error" in rendered
        assert "[ CHANGE [ONE] ]" in rendered
        assert "Review [not markup] before applying." in rendered
        assert "[ ERROR E[1] ]" in rendered
        assert "Retry [later]" in rendered


def test_action_bar_rejects_raw_or_modal_buttons() -> None:
    with pytest.raises(TypeError, match="PanelButton"):
        ActionBar(ModalButton("Wrong context"))  # type: ignore[arg-type]


async def test_semantic_table_uses_literal_cells_and_explicit_empty_state() -> None:
    app = _TableApp()
    async with app.run_test(size=(80, 24)):
        populated = app.query_one("#populated-table-view", TableView)
        table = populated.query_one(SemanticDataTable)
        assert table.has_class("data-table")
        assert table.fixed_rows == 0
        assert str(table.get_cell_at(Coordinate(0, 0))) == "alpha[1]"
        assert str(table.get_cell_at(Coordinate(0, 1))) == "C:/memory/[alpha].md"

        empty = app.query_one("#empty-table-view", TableView).query_one(EmptyState)
        assert empty.has_class("empty-state")
        assert "No rows matched [literal]." in _rendered_text(empty)


async def test_table_rejects_row_shape_mismatch_and_can_replace_rows() -> None:
    columns = (TableColumn("name", "NAME"), TableColumn("path", "PATH"))
    with pytest.raises(ValueError, match="expected 2"):
        SemanticDataTable(columns, (TableRow(("only one",)),))

    table = SemanticDataTable(columns, (TableRow(("one", "first"), key="one"),))

    class _ReplaceApp(App[None]):
        def compose(self) -> ComposeResult:
            yield table

    async with _ReplaceApp().run_test():
        table.replace_rows((TableRow(("two[2]", "second"), key="two"),))
        assert str(table.get_cell_at(Coordinate(0, 0))) == "two[2]"


async def test_typed_confirmation_is_keyboard_first_and_never_applies_on_input_enter() -> None:
    modal = PreviewConfirmScreen(
        _preview(),
        current_fingerprint="state[1]",
        typed_confirmation="delete [safe]",
        confirm_label="DELETE",
        confirm_tone="destructive",
    )
    app = _ModalHostApp(modal)
    assert modal.can_confirm is False

    async with app.run_test(size=(40, 10)) as pilot:
        await pilot.pause()
        dialog = modal.query_one(".preview-confirm-dialog")
        assert dialog.region.x >= 0
        assert dialog.region.y >= 0
        assert dialog.region.right <= 40
        assert dialog.region.bottom <= 10

        cancel = modal.query_one(f"#{modal.CANCEL_ID}", ModalButton)
        confirm = modal.query_one(f"#{modal.CONFIRM_ID}", ModalButton)
        field = modal.query_one(f"#{ConfirmationBlock.INPUT_ID}", TuiInput)
        assert app.focused is cancel
        assert confirm.disabled

        field.focus()
        await pilot.press(
            "d",
            "e",
            "l",
            "e",
            "t",
            "e",
            "space",
            "left_square_bracket",
            "s",
            "a",
            "f",
            "e",
            "right_square_bracket",
        )
        assert field.value == "delete [safe]"
        assert not confirm.disabled

        await pilot.press("enter")
        assert app.screen is modal
        assert app.focused is confirm

        await pilot.press("enter")
        await pilot.pause()
        assert app.decision is True
        assert app.focused is app.query_one("#modal-opener", PanelButton)


async def test_verified_confirmation_without_typed_text_still_defaults_to_cancel() -> None:
    modal = PreviewConfirmScreen(_preview(), current_fingerprint="state[1]")
    app = _ModalHostApp(modal)

    async with app.run_test(size=(48, 12)) as pilot:
        await pilot.pause()
        cancel = modal.query_one(f"#{modal.CANCEL_ID}", ModalButton)
        confirm = modal.query_one(f"#{modal.CONFIRM_ID}", ModalButton)
        assert app.focused is cancel
        assert not confirm.disabled

        await pilot.press("left")
        assert app.focused is confirm
        await pilot.press("enter")
        await pilot.pause()
        assert app.decision is True


async def test_fingerprint_mismatch_is_literal_disables_apply_and_restores_focus() -> None:
    modal = PreviewConfirmScreen(
        _preview(fingerprint="before[1]"),
        current_fingerprint="after[2]",
        typed_confirmation="delete [safe]",
        confirm_tone="destructive",
        border_style="ascii",
    )
    app = _ModalHostApp(modal)

    async with app.run_test(size=(32, 8)) as pilot:
        await pilot.pause()
        block = modal.query_one(f"#{modal.BLOCK_ID}", ConfirmationBlock)
        confirm = modal.query_one(f"#{modal.CONFIRM_ID}", ModalButton)
        field = modal.query_one(f"#{ConfirmationBlock.INPUT_ID}", TuiInput)

        assert block.has_class("fingerprint-mismatch")
        assert block.styles.border_top[0] == "ascii"
        assert confirm.disabled
        assert field.disabled
        rendered = _rendered_text(block)
        assert "[ STATE CHANGED ]" in rendered
        assert "before[1]" in rendered
        assert "after[2]" in rendered
        composited = _composited_text(app)
        assert "STATE CHANGED" in composited
        assert "APPLY" in composited
        assert "CANCEL" in composited
        for button in (confirm, modal.query_one(f"#{modal.CANCEL_ID}", ModalButton)):
            assert button.region.y >= 0
            assert button.region.bottom <= 8

        for _ in range(4):
            await pilot.press("tab")
            assert app.focused is not None
            assert app.focused.screen is modal

        await pilot.press("escape")
        await pilot.pause()
        assert app.decision is False
        assert app.focused is app.query_one("#modal-opener", PanelButton)


@pytest.mark.parametrize("border_style", ["solid", "ascii"])
async def test_typed_confirmation_remains_operable_at_32_by_8(
    border_style: BorderStyle,
) -> None:
    modal = PreviewConfirmScreen(
        _preview(),
        current_fingerprint="state[1]",
        typed_confirmation="confirm",
        border_style=border_style,
    )
    app = _ModalHostApp(modal)

    async with app.run_test(size=(32, 8)) as pilot:
        await pilot.pause()
        field = modal.query_one(f"#{ConfirmationBlock.INPUT_ID}", TuiInput)
        confirm = modal.query_one(f"#{modal.CONFIRM_ID}", ModalButton)
        cancel = modal.query_one(f"#{modal.CANCEL_ID}", ModalButton)

        field.focus()
        assert confirm.region.bottom <= 8
        assert cancel.region.bottom <= 8

        await pilot.press("c", "o", "n", "f", "i", "r", "m")
        await pilot.pause()
        assert field.value == "confirm"
        assert field.region.height == 1
        assert field.styles.border_top[0] != "ascii"
        assert field.region.y >= 0
        assert field.region.bottom <= 8
        assert "confirm" in _composited_text(app)

        await pilot.press("enter")
        assert app.focused is confirm
        await pilot.press("enter")
        await pilot.pause()
        assert app.decision is True


def test_phase3_widget_css_uses_semantic_layers_without_control_id_styling() -> None:
    styles = Path(__file__).parents[1] / "src" / "memtomem" / "tui" / "styles"
    layout = (styles / "layout.tcss").read_text(encoding="utf-8")
    components = (styles / "components.tcss").read_text(encoding="utf-8")
    states = (styles / "states.tcss").read_text(encoding="utf-8")
    combined = "\n".join((layout, components, states))

    for semantic_class in (
        ".form-row",
        ".action-bar",
        ".data-table",
        ".preview-block",
        ".confirmation-block",
        ".error-state",
        ".empty-state",
    ):
        assert semantic_class in combined

    assert ".form-row" in layout
    assert ".data-table" in components
    assert ".confirmation-block.confirmation-valid" in states
    assert "#preview-confirm-apply" not in combined
    assert "#preview-confirm-cancel" not in combined
    assert "#confirmation-input" not in combined
