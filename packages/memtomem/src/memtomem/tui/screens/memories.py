"""Native Search presentation for the independent Memories destination."""

from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import Any, Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Input, Static

from memtomem.tui.application.contracts import (
    OperationResult,
    OperationSnapshot,
    OperationStatus,
    UserSafeError,
)
from memtomem.tui.application.operations import (
    OperationConflictError,
    OperationHandle,
    OperationRunner,
    OperationRunnerClosedError,
)
from memtomem.tui.application.search import (
    SearchPreflight,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchService,
)
from memtomem.tui.widgets.controls import PanelButton, TuiInput
from memtomem.tui.widgets.forms import ActionBar, FormRow
from memtomem.tui.widgets.operation_status import (
    OperationStateBlock,
    OperationStatePresentation,
)
from memtomem.tui.widgets.preview import EmptyState, ErrorState, NoticeBlock
from memtomem.tui.widgets.tables import TableColumn, TableRow, TableView


_RESULT_COLUMNS = (
    TableColumn("rank", "RANK", width=6),
    TableColumn("score", "SCORE", width=9),
    TableColumn("source", "SOURCE", width=28),
    TableColumn("content", "CONTENT", width=48),
)


def _optional_text(value: str) -> str | None:
    return value or None


def _literal(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _content_preview(content: str) -> str:
    """Mirror the CLI table's mechanical 60-character single-line preview."""
    return content[:60].replace("\n", " ")


class MemoriesSurface(VerticalScroll, can_focus=True):
    """Persistent Search form, lifecycle, warnings, and result list."""

    class SelectionChanged(Message):
        def __init__(
            self,
            item: SearchResultItem | None,
            response: SearchResponse | None,
        ) -> None:
            super().__init__()
            self.item = item
            self.response = response

    def __init__(self, search: SearchService, runner: OperationRunner) -> None:
        super().__init__(id="memories-surface", classes="route-surface memories-surface")
        self.search = search
        self.runner = runner
        self.preflight: SearchPreflight = search.preflight()
        self.response: SearchResponse | None = None
        self._items_by_id: dict[str, SearchResultItem] = {}
        self._operation_id: str | None = None
        self._unsubscribe: Any | None = None
        self._reveal_generation = 0

    def compose(self) -> ComposeResult:
        default_top_k = self.preflight.default_top_k
        top_k_value = "" if default_top_k is None else str(default_top_k)
        top_k_help = (
            "Configured memtomem default is unavailable."
            if default_top_k is None
            else f"Configured memtomem default: {default_top_k}."
        )
        yield Static("[ MEMORIES / SEARCH ]", classes="section-title", markup=False)
        yield NoticeBlock(
            self._preflight_title(),
            self.preflight.message,
            tone=self._preflight_tone(),
            id="search-runtime-notice",
            classes="inline-notice",
        )
        yield FormRow(
            "Query",
            TuiInput(
                placeholder="Search query",
                id="search-query",
                classes="text-input",
            ),
            supporting_text="Search uses the complete memtomem retrieval pipeline.",
            classes="compact-form-row",
        )
        with Horizontal(classes="filter-grid"):
            with Vertical(classes="filter-column"):
                yield FormRow(
                    "Top K",
                    TuiInput(value=top_k_value, id="search-top-k", classes="text-input"),
                    supporting_text=top_k_help,
                    classes="compact-form-row",
                )
                yield FormRow(
                    "Source",
                    TuiInput(id="search-source", classes="text-input"),
                    classes="compact-form-row",
                )
                yield FormRow(
                    "Tag",
                    TuiInput(
                        placeholder="tag-a,tag-b",
                        id="search-tag",
                        classes="text-input",
                    ),
                    classes="compact-form-row",
                )
            with Vertical(classes="filter-column"):
                yield FormRow(
                    "Namespace",
                    TuiInput(id="search-namespace", classes="text-input"),
                    classes="compact-form-row",
                )
                yield FormRow(
                    "Scope",
                    TuiInput(
                        placeholder="user,project_local or project_*",
                        id="search-scope",
                        classes="text-input",
                    ),
                    classes="compact-form-row",
                )
                yield FormRow(
                    "As of",
                    TuiInput(
                        placeholder="YYYY-MM-DD or YYYY-QN",
                        id="search-as-of",
                        classes="text-input",
                    ),
                    classes="compact-form-row",
                )
        yield ActionBar(
            PanelButton(
                self._action_label(),
                id="search-submit",
                classes="action-button cyan",
                disabled=(
                    self.preflight.setup_required or self.preflight.readiness_error is not None
                ),
            )
        )
        yield OperationStateBlock(
            OperationStatePresentation(
                OperationStatus.QUEUED,
                "Search has not started.",
            ),
            id="search-operation-state",
        )
        yield Vertical(id="search-error-host", classes="feedback-stack")
        yield Vertical(id="search-warning-list", classes="notice-stack")
        yield Static("", id="search-result-summary", classes="result-summary muted", markup=False)
        yield TableView(
            _RESULT_COLUMNS,
            empty_title="SEARCH READY",
            empty_message="Enter a query and run Search. No indexing or embedding repair is automatic.",
            id="search-results",
            classes="result-table-view",
        )

    def on_mount(self) -> None:
        self.query_one("#search-operation-state", OperationStateBlock).display = False
        self.query_one("#search-error-host", Vertical).display = False
        self.query_one("#search-warning-list", Vertical).display = False
        self._unsubscribe = self.runner.subscribe(self._on_operation_snapshot)

    def on_unmount(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def on_button_pressed(self, event: PanelButton.Pressed) -> None:
        if event.button.id == "search-submit":
            await self.start_search()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id and event.input.id.startswith("search-"):
            await self.start_search()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        item = self._items_by_id.get(str(event.row_key.value))
        if item is not None:
            self.post_message(self.SelectionChanged(item, self.response))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        item = self._items_by_id.get(str(event.row_key.value))
        if item is not None:
            self.post_message(self.SelectionChanged(item, self.response))

    async def start_search(self) -> None:
        """Validate raw CLI-equivalent inputs and submit non-cancellable work."""
        button = self.query_one("#search-submit", PanelButton)
        if button.disabled or self._operation_id is not None:
            return
        try:
            request = SearchRequest.from_raw(
                self.query_one("#search-query", TuiInput).value,
                self.query_one("#search-top-k", TuiInput).value,
                source_filter=_optional_text(self.query_one("#search-source", TuiInput).value),
                tag_filter=_optional_text(self.query_one("#search-tag", TuiInput).value),
                namespace=_optional_text(self.query_one("#search-namespace", TuiInput).value),
                scope=_optional_text(self.query_one("#search-scope", TuiInput).value),
                as_of=_optional_text(self.query_one("#search-as-of", TuiInput).value),
                # Clicking the explicitly labelled disclosure action is the consent event.
                allow_runtime_initialization=self.preflight.requires_consent,
            )
        except (TypeError, ValueError):
            await self._show_error(
                UserSafeError(
                    code="search.input.invalid",
                    message="Top K must be an integer.",
                    recovery_action="Enter an integer Top K value and try again.",
                    retryable=True,
                )
            )
            return

        await self._prepare_for_search()
        try:
            handle = self.runner.start(
                self.search.operation_spec(request),
                request,
                self.search.execute,
            )
        except OperationConflictError:
            await self._show_error(
                UserSafeError(
                    code="search.operation.conflict",
                    message="Another conflicting operation is already running.",
                    recovery_action="Wait for the active operation and try Search again.",
                    retryable=True,
                )
            )
            button.disabled = False
            return
        except OperationRunnerClosedError:
            await self._show_error(
                UserSafeError(
                    code="search.operation.closed",
                    message="Search cannot start while the application is closing.",
                    retryable=False,
                )
            )
            button.disabled = False
            return

        self._operation_id = handle.id
        self._show_operation_snapshot(handle.snapshot)
        self.run_worker(
            partial(self._await_result, handle),  # type: ignore[arg-type]
            group="memories-search-result",
            exclusive=True,
        )

    async def _prepare_for_search(self) -> None:
        self.query_one("#search-submit", PanelButton).disabled = True
        await self._show_error(None)
        await self._show_warnings(())
        view = self.query_one("#search-results", TableView)
        view.set_empty_state("SEARCHING", "The complete search pipeline is running.")
        view.replace_rows(())
        self.response = None
        self._items_by_id.clear()
        self.query_one("#search-result-summary", Static).update("")
        self.post_message(self.SelectionChanged(None, None))
        operation = self.query_one("#search-operation-state", OperationStateBlock)
        operation.display = True
        operation.update_presentation(
            OperationStatePresentation(
                OperationStatus.QUEUED,
                "Search is queued. This operation is not cancellable.",
            )
        )
        self._reveal(operation)

    async def _await_result(self, handle: OperationHandle[SearchResponse]) -> None:
        result = await handle.result()
        if handle.id != self._operation_id:
            return
        await self._apply_result(result)
        self._operation_id = None
        self.query_one("#search-submit", PanelButton).disabled = False
        self.refresh_preflight()

    def _on_operation_snapshot(self, snapshot: OperationSnapshot) -> None:
        if snapshot.id == self._operation_id and self.is_mounted:
            self._show_operation_snapshot(snapshot)

    def _show_operation_snapshot(self, snapshot: OperationSnapshot) -> None:
        progress = snapshot.progress
        messages = {
            OperationStatus.QUEUED: "Search is queued. This operation is not cancellable.",
            OperationStatus.RUNNING: "Searching the full pipeline. This operation is not cancellable.",
            OperationStatus.SUCCEEDED: "Search completed.",
            OperationStatus.PARTIAL: "Search completed with retrieval degradation.",
            OperationStatus.FAILED: "Search failed.",
            OperationStatus.CANCELLING: "Search cancellation is not available in Phase 4.",
            OperationStatus.CANCELLED: "Search stopped.",
        }
        message = progress.message if progress and progress.message else messages[snapshot.status]
        self.query_one("#search-operation-state", OperationStateBlock).update_presentation(
            OperationStatePresentation(
                snapshot.status,
                message,
                completed=progress.completed if progress else 0,
                remaining=progress.remaining if progress else None,
                skipped=progress.skipped if progress else 0,
                failed=progress.failed if progress else 0,
                recovery=snapshot.recovery_action,
            )
        )

    async def _apply_result(self, result: OperationResult[SearchResponse]) -> None:
        await self._show_warnings(result.warnings)
        if result.status is OperationStatus.FAILED:
            await self._show_error(result.error)
            view = self.query_one("#search-results", TableView)
            view.set_empty_state("SEARCH FAILED", "No result set was produced.")
            view.replace_rows(())
            self.post_message(self.SelectionChanged(None, None))
            return

        response = result.value
        if response is None:
            view = self.query_one("#search-results", TableView)
            view.set_empty_state("NO RESULTS", "Search completed without a result set.")
            view.replace_rows(())
            self.post_message(self.SelectionChanged(None, None))
            self._reveal(view)
            return

        self.response = response
        self._items_by_id = {item.chunk_id: item for item in response.items}
        rows = tuple(
            TableRow(
                (
                    item.rank,
                    f"{item.score:.4f}",
                    item.source_file or "-",
                    _content_preview(item.content),
                ),
                key=item.chunk_id,
            )
            for item in response.items
        )
        view = self.query_one("#search-results", TableView)
        view.set_empty_state("NO MATCHES", "No memories matched the current query and filters.")
        view.replace_rows(rows)
        stats = response.stats
        self.query_one("#search-result-summary", Static).update(
            " | ".join(
                (
                    f"Results {len(response.items)}",
                    f"BM25 {stats.bm25_candidates}",
                    f"Dense {stats.dense_candidates}",
                    f"Fused {stats.fused_total}",
                    f"Final {stats.final_total}",
                    f"Hidden system namespaces {stats.hidden_system_namespaces}",
                )
            )
        )
        if response.items:
            view.table.move_cursor(row=0, column=0, animate=False)
            self.post_message(self.SelectionChanged(response.items[0], response))
        else:
            self.post_message(self.SelectionChanged(None, response))
        target = self.query_one("#search-warning-list", Vertical) if result.warnings else view
        self._reveal(target)

    async def _show_error(self, error: UserSafeError | None) -> None:
        host = self.query_one("#search-error-host", Vertical)
        await host.remove_children()
        if error is None:
            host.display = False
            return
        await host.mount(
            ErrorState(
                error.code,
                error.message,
                recovery=error.recovery_action,
            )
        )
        host.display = True
        self._reveal(host)

    async def _show_warnings(self, warnings: tuple[Any, ...]) -> None:
        host = self.query_one("#search-warning-list", Vertical)
        await host.remove_children()
        if not warnings:
            host.display = False
            return
        await host.mount(
            *(
                NoticeBlock(
                    warning.code,
                    warning.message,
                    tone="warning",
                    recovery=warning.recovery_action,
                )
                for warning in warnings
            )
        )
        host.display = True

    def _reveal(self, widget: Any) -> None:
        """Keep the current lifecycle, feedback, or result visible in compact layouts."""

        self._reveal_generation += 1
        generation = self._reveal_generation
        self.call_after_refresh(
            self._apply_reveal,
            widget,
            generation,
        )

    def _apply_reveal(self, widget: Any, generation: int) -> None:
        """Apply only the newest post-refresh reveal request."""

        if generation != self._reveal_generation or not self.is_mounted:
            return
        self.scroll_to_widget(
            widget,
            animate=False,
            immediate=True,
            force=True,
            top=True,
        )

    def refresh_preflight(self) -> None:
        """Refresh disclosure copy without running Search or opening storage."""
        self.preflight = self.search.preflight()
        notice = self.query_one("#search-runtime-notice", NoticeBlock)
        notice.update_notice(
            self._preflight_title(),
            self.preflight.message,
            tone=self._preflight_tone(),
        )
        button = self.query_one("#search-submit", PanelButton)
        button.label = self._action_label()
        button.disabled = (
            self.preflight.setup_required
            or self.preflight.readiness_error is not None
            or self._operation_id is not None
        )

    def _action_label(self) -> str:
        if self.preflight.readiness_error is not None:
            return "CONFIG ERROR"
        if self.preflight.setup_required:
            return "SETUP REQUIRED"
        return "INITIALIZE & SEARCH" if self.preflight.requires_consent else "SEARCH"

    def _preflight_title(self) -> str:
        if self.preflight.readiness_error is not None:
            return "CONFIGURATION UNREADABLE"
        if self.preflight.setup_required:
            return "SETUP REQUIRED"
        return "RUNTIME TRANSITION" if self.preflight.requires_consent else "RUNTIME READY"

    def _preflight_tone(self) -> Literal["ok", "warning", "error"]:
        if self.preflight.readiness_error is not None:
            return "error"
        return (
            "warning" if self.preflight.setup_required or self.preflight.requires_consent else "ok"
        )


class MemoryDetailsSurface(VerticalScroll, can_focus=True):
    """Full literal content and metadata for the selected Search result."""

    def __init__(self) -> None:
        super().__init__(id="memory-details-surface", classes="route-surface details-surface")
        self.selected_item: SearchResultItem | None = None

    def compose(self) -> ComposeResult:
        yield Static("[ SEARCH DETAILS ]", classes="section-title", markup=False)
        yield EmptyState(
            "NO SELECTION",
            "Run Search and select a result in Main. F4 moves focus to Details.",
            id="memory-detail-empty",
        )
        yield Vertical(id="memory-detail-body", classes="detail-stack")

    def on_mount(self) -> None:
        self.query_one("#memory-detail-body", Vertical).display = False

    async def show_item(
        self,
        item: SearchResultItem | None,
        response: SearchResponse | None,
    ) -> None:
        self.selected_item = item
        empty = self.query_one("#memory-detail-empty", EmptyState)
        body = self.query_one("#memory-detail-body", Vertical)
        await body.remove_children()
        if item is None:
            empty.display = True
            body.display = False
            return

        metadata = (
            ("ID", item.chunk_id),
            ("Rank", item.rank),
            ("Score", f"{item.score:.6f}"),
            ("Retrieval source", item.retrieval_source),
            ("Source file", item.source_file),
            ("Heading", " > ".join(item.heading_hierarchy) or None),
            ("Chunk type", item.chunk_type),
            ("Lines", f"{_literal(item.start_line)} .. {_literal(item.end_line)}"),
            ("Language", item.language),
            ("Tags", ", ".join(item.tags) or None),
            ("Namespace", item.namespace),
            ("Scope", item.scope),
            ("Project root", item.project_root),
            ("Valid from (Unix)", item.valid_from_unix),
            ("Valid to (Unix)", item.valid_to_unix),
            ("Created", item.created_at),
            ("Updated", item.updated_at),
            ("Via session summary", "yes" if item.via_session_summary else "no"),
            (
                "Project context",
                response.project_context_root if response is not None else None,
            ),
        )
        children: list[Static] = [
            Static("[ FULL CONTENT ]", classes="detail-heading", markup=False),
            Static(item.content, classes="memory-content", markup=False),
            Static("[ METADATA ]", classes="detail-heading", markup=False),
        ]
        children.extend(
            Static(
                f"{label}: {_literal(value)}",
                classes="metadata-row",
                markup=False,
            )
            for label, value in metadata
        )
        if item.context is not None:
            context = item.context
            children.extend(
                (
                    Static("[ CONTEXT WINDOW ]", classes="detail-heading", markup=False),
                    Static(
                        " | ".join(
                            (
                                f"Tier {_literal(context.context_tier_used)}",
                                f"Position {context.chunk_position}/{context.total_chunks_in_file}",
                                f"Siblings {context.sibling_count}",
                            )
                        ),
                        classes="metadata-row",
                        markup=False,
                    ),
                )
            )
            if context.parent_heading is not None:
                children.append(
                    Static(
                        f"Parent heading: {context.parent_heading}",
                        classes="metadata-row",
                        markup=False,
                    )
                )
            if context.parent_content is not None:
                children.extend(
                    (
                        Static("Parent content", classes="detail-heading", markup=False),
                        Static(context.parent_content, classes="memory-content", markup=False),
                    )
                )
            for direction, chunks in (
                ("BEFORE", context.window_before),
                ("AFTER", context.window_after),
            ):
                if not chunks:
                    continue
                children.append(
                    Static(f"[ CONTEXT {direction} ]", classes="detail-heading", markup=False)
                )
                for chunk in chunks:
                    children.extend(
                        (
                            Static(
                                f"{chunk.chunk_id} | {chunk.source_file} | "
                                f"lines {chunk.start_line}..{chunk.end_line} | "
                                f"{' > '.join(chunk.heading_hierarchy) or '-'}",
                                classes="metadata-row",
                                markup=False,
                            ),
                            Static(chunk.content, classes="memory-content", markup=False),
                        )
                    )
        if response is not None:
            stats = response.stats
            children.extend(
                (
                    Static("[ SEARCH STATS ]", classes="detail-heading", markup=False),
                    Static(
                        " | ".join(
                            (
                                f"BM25 {stats.bm25_candidates}",
                                f"Dense {stats.dense_candidates}",
                                f"Fused {stats.fused_total}",
                                f"Final {stats.final_total}",
                                f"Indexed chunks {_literal(stats.indexed_chunks)}",
                                f"Dense chunks {_literal(stats.dense_chunks)}",
                            )
                        ),
                        classes="metadata-row",
                        markup=False,
                    ),
                )
            )
        await body.mount(*children)
        empty.display = False
        body.display = True


__all__ = ["MemoriesSurface", "MemoryDetailsSurface"]
