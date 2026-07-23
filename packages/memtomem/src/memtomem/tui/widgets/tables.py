"""Literal, structured table presenters shared by TUI feature screens."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable

from memtomem.tui.widgets.preview import EmptyState


def _with_semantic_class(semantic_class: str, classes: str | None) -> str:
    return f"{semantic_class} {classes or ''}".strip()


@dataclass(frozen=True)
class TableColumn:
    """A stable table column definition."""

    key: str
    label: str
    width: int | None = None


@dataclass(frozen=True)
class TableRow:
    """A stable table row whose values are rendered as literal text."""

    cells: tuple[object, ...]
    key: str | None = None


class SemanticDataTable(DataTable[object]):
    """Dense row-oriented table that never treats cell strings as markup."""

    def __init__(
        self,
        columns: tuple[TableColumn, ...],
        rows: tuple[TableRow, ...] = (),
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        if not columns:
            raise ValueError("SemanticDataTable requires at least one column")
        self._presented_columns = columns
        self._presented_rows = self._validate_rows(rows)
        super().__init__(
            show_header=True,
            show_row_labels=False,
            fixed_rows=0,
            zebra_stripes=True,
            cursor_type="row",
            cell_padding=1,
            name=name,
            id=id,
            classes=_with_semantic_class("data-table", classes),
            disabled=disabled,
        )

    def on_mount(self) -> None:
        for column in self._presented_columns:
            self.add_column(Text(column.label), key=column.key, width=column.width)
        self._add_presented_rows()

    async def _on_click(self, event: events.Click) -> None:
        """Synchronize the shell section before DataTable consumes the click."""
        synchronize = getattr(self.app, "synchronize_pointer_target", None)
        if synchronize is not None:
            synchronize(self)
        await super()._on_click(event)

    def replace_rows(self, rows: tuple[TableRow, ...]) -> None:
        """Replace only presented rows; callers remain responsible for domain state."""
        self._presented_rows = self._validate_rows(rows)
        if self.is_mounted:
            self.clear()
            self._add_presented_rows()

    def _validate_rows(self, rows: tuple[TableRow, ...]) -> tuple[TableRow, ...]:
        expected = len(self._presented_columns)
        for row in rows:
            if len(row.cells) != expected:
                raise ValueError(f"table row has {len(row.cells)} cells; expected {expected}")
        return rows

    def _add_presented_rows(self) -> None:
        for row in self._presented_rows:
            cells = tuple(Text(str(value)) for value in row.cells)
            self.add_row(*cells, key=row.key)


class TableView(Vertical):
    """Show a semantic data table or an explicit empty state."""

    def __init__(
        self,
        columns: tuple[TableColumn, ...],
        rows: tuple[TableRow, ...] = (),
        *,
        empty_title: str = "NO DATA",
        empty_message: str = "No rows are available.",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        if not columns:
            raise ValueError("TableView requires at least one column")
        super().__init__(
            name=name,
            id=id,
            classes=_with_semantic_class("data-table-view", classes),
            disabled=disabled,
        )
        self.columns = columns
        self.rows = rows
        self.empty_title = empty_title
        self.empty_message = empty_message

    def compose(self) -> ComposeResult:
        yield SemanticDataTable(self.columns, self.rows)
        yield EmptyState(self.empty_title, self.empty_message)

    def on_mount(self) -> None:
        self._sync_visibility()

    @property
    def table(self) -> SemanticDataTable:
        """Return the stable table mounted for the lifetime of this view."""
        return self.query_one(SemanticDataTable)

    def replace_rows(self, rows: tuple[TableRow, ...]) -> None:
        """Replace rows without replacing the table or losing route state."""
        self.rows = rows
        if self.is_mounted:
            self.table.replace_rows(rows)
            self._sync_visibility()

    def set_empty_state(self, title: str, message: str) -> None:
        """Update the literal empty-state copy used for the current lifecycle."""
        self.empty_title = title
        self.empty_message = message
        if not self.is_mounted:
            return
        empty = self.query_one(EmptyState)
        empty.title = title
        empty.message = message
        statics = list(empty.query("Static"))
        if len(statics) >= 2:
            statics[0].update(f"[ {title} ]")
            statics[1].update(message)

    def _sync_visibility(self) -> None:
        table = self.table
        empty = self.query_one(EmptyState)
        table.display = bool(self.rows)
        empty.display = not self.rows
