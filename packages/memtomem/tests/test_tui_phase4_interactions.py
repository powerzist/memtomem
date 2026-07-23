"""Rendered Phase 4 Home/Search routing, lifecycle, focus, and mouse tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.coordinate import Coordinate
from textual.widgets import Static

from memtomem.tui.application.contracts import (
    OperationResult,
    OperationSpec,
    UserSafeError,
    UserSafeWarning,
)
from memtomem.tui.application.diagnostics import (
    DatabaseDiagnostic,
    DatabaseState,
    DenseCoverage,
    DiagnosticsSnapshot,
    SchemaDiagnostic,
    SchemaState,
    SetupDiagnostic,
    SetupState,
)
from memtomem.tui.application.runtime import RuntimeManager
from memtomem.tui.application.search import (
    SearchPreflight,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchStats,
)
from memtomem.tui.runtime import TuiPaths
from memtomem.tui.screens.home import HomeDetailsSurface, HomeSurface
from memtomem.tui.screens.memories import MemoriesSurface, MemoryDetailsSurface
from memtomem.tui.screens.shell import MemtomemTuiApp
from memtomem.tui.terminal import BorderStyle
from memtomem.tui.widgets.controls import PanelButton, TuiInput
from memtomem.tui.widgets.operation_status import OperationStateBlock
from memtomem.tui.widgets.preview import NoticeBlock
from memtomem.tui.widgets.tables import TableView


def _paths(tmp_path: Path) -> TuiPaths:
    root = tmp_path / ".dev" / ".memtomem"
    return TuiPaths(
        mode="dev",
        project_root=tmp_path,
        state_root=root,
        config_path=root / "config.json",
        config_d_path=root / "config.d",
        database_path=root / "memtomem.db",
        memories_path=root / "memories",
    )


class _Diagnostics:
    def __init__(self, snapshot: DiagnosticsSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    async def inspect(self) -> DiagnosticsSnapshot:
        self.calls += 1
        return self.snapshot


class _Search:
    def __init__(
        self,
        result: OperationResult[SearchResponse],
        *,
        setup_required: bool = False,
        default_top_k: int | None = 10,
        readiness_error: UserSafeError | None = None,
    ) -> None:
        self.result = result
        self.started = False
        self.setup_required = setup_required
        self.default_top_k = default_top_k
        self.readiness_error = readiness_error
        self.requests: list[SearchRequest] = []

    def preflight(self) -> SearchPreflight:
        blocked = self.setup_required or self.readiness_error is not None
        return SearchPreflight(
            runtime_started=self.started,
            setup_required=self.setup_required,
            requires_consent=not self.started and not blocked,
            may_initialize_storage=not self.started and not blocked,
            may_migrate_schema=not self.started and not blocked,
            auto_index=False,
            auto_build_missing_embeddings=False,
            default_top_k=self.default_top_k,
            readiness_error=self.readiness_error,
            message=(
                (
                    "Search cannot start because configuration could not be read safely. "
                    "Review config.json and config.d before trying again."
                )
                if self.readiness_error is not None
                else "Search setup is required before starting Search."
                if self.setup_required
                else (
                    "Starting Search may initialize or migrate storage; no automatic indexing "
                    "or embedding construction occurs."
                    if not self.started
                    else "Search runtime is active; automatic indexing remains disabled."
                )
            ),
        )

    @staticmethod
    def operation_spec(request: SearchRequest) -> OperationSpec:
        return OperationSpec(name="Search memories", cancellable=False)

    async def execute(
        self, request: SearchRequest, context: object
    ) -> OperationResult[SearchResponse]:
        self.requests.append(request)
        self.started = True
        return self.result


def _snapshot(paths: TuiPaths, *, default_top_k: int = 10) -> DiagnosticsSnapshot:
    return DiagnosticsSnapshot(
        setup=SetupDiagnostic(SetupState.CONFIGURED, paths.config_path, (paths.memories_path,)),
        database=DatabaseDiagnostic(DatabaseState.READABLE, paths.database_path),
        schema=SchemaDiagnostic(SchemaState.READY),
        storage_backend="sqlite",
        default_top_k=default_top_k,
        rrf_k=60,
        tokenizer="unicode61",
        scheduler_enabled=True,
        health_watchdog_enabled=False,
        chunks=12,
        sources=3,
        orphans=0,
        dense_coverage=DenseCoverage(total=12, with_dense=8),
        warnings=(
            UserSafeWarning(
                code="diagnostics.scheduler_inactive",
                message="Schedules are enabled, but the health watchdog is disabled.",
                recovery_action="Enable the health watchdog before relying on schedules.",
            ),
        ),
    )


def _item(chunk_id: str, rank: int, content: str) -> SearchResultItem:
    return SearchResultItem(
        chunk_id=chunk_id,
        rank=rank,
        score=1.0 / rank,
        retrieval_source="hybrid",
        source_file=f"C:/memory/{chunk_id}.md",
        content=content,
        heading_hierarchy=("Heading", chunk_id),
        chunk_type="section",
        start_line=rank,
        end_line=rank + 3,
        language="en",
        tags=("tag",),
        namespace="default",
        scope="user",
        project_root=None,
        valid_from_unix=None,
        valid_to_unix=None,
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
        updated_at=datetime(2026, 7, 18, tzinfo=UTC),
        via_session_summary=False,
        context=None,
    )


def _response() -> SearchResponse:
    items = (
        _item("first[1]", 1, "first full [literal] content"),
        _item("second[2]", 2, "second full [literal] content"),
    )
    return SearchResponse(
        query="memory query",
        items=items,
        stats=SearchStats(8, 7, 9, 2, 1, 20, 15),
        project_context_root=None,
    )


def _app(
    tmp_path: Path,
    *,
    result: OperationResult[SearchResponse] | None = None,
    setup_required: bool = False,
    border_style: BorderStyle = "solid",
    default_top_k: int = 10,
    readiness_error: UserSafeError | None = None,
) -> tuple[MemtomemTuiApp, _Diagnostics, _Search, RuntimeManager[object]]:
    paths = _paths(tmp_path)
    diagnostics = _Diagnostics(_snapshot(paths, default_top_k=default_top_k))
    search = _Search(
        result or OperationResult.succeeded(_response()),
        setup_required=setup_required,
        default_top_k=default_top_k,
        readiness_error=readiness_error,
    )
    runtime = RuntimeManager[object](paths)
    app = MemtomemTuiApp(
        border_style=border_style,
        startup_refresh=True,
        terminal_profile="windows-terminal",
        paths=paths,
        runtime_manager=runtime,
        diagnostics_service=diagnostics,  # type: ignore[arg-type]
        search_service=search,  # type: ignore[arg-type]
    )
    return app, diagnostics, search, runtime


async def test_phase4_internal_components_inherit_ascii_border_mode(tmp_path: Path) -> None:
    app, _diagnostics, _search, _runtime = _app(tmp_path, border_style="ascii")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        home = app.query_one(HomeSurface)
        assert home.query_one(NoticeBlock).styles.border_top[0] == "ascii"
        assert home.query_one(".status-row").styles.border_bottom[0] == "ascii"

        await pilot.click("#route-memories")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        assert surface.query_one("#search-runtime-notice", NoticeBlock).styles.border_top[0] == (
            "ascii"
        )
        assert surface.query_one("#search-operation-state").styles.border_top[0] == "ascii"
        assert surface.query_one("#search-results .empty-state").styles.border_top[0] == "ascii"

        surface.query_one("#search-top-k", TuiInput).value = "invalid"
        await surface.start_search()
        await pilot.pause()
        assert surface.query_one("#search-error-host .error-state").styles.border_top[0] == "ascii"

        surface.query_one("#search-top-k", TuiInput).value = "10"
        await surface.start_search()
        await pilot.pause()
        assert app.query_one("#memory-detail-body .memory-content").styles.border_top[0] == "ascii"


@pytest.mark.parametrize(
    "size",
    [
        (160, 50),
        (120, 30),
        (100, 24),
        (99, 24),
        (80, 20),
        (60, 16),
        (48, 12),
        (40, 10),
        (32, 8),
    ],
)
async def test_phase4_home_and_search_render_across_required_viewports(
    tmp_path: Path,
    size: tuple[int, int],
) -> None:
    app, diagnostics, _search, runtime = _app(tmp_path)
    width, height = size
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.activate_section("main")
        await pilot.pause()

        strips = app.screen._compositor.render_strips()
        home_text = "\n".join(strip.text for strip in strips)
        assert len(strips) == height
        assert all(len(strip.text) <= width for strip in strips)
        assert "HOME / STATUS" in home_text
        assert app.query_one(HomeSurface).display
        assert diagnostics.calls == 1
        assert not runtime.started

        app.state.route_id = "memories"
        app._update_route_classes()
        app.activate_section("main")
        await pilot.pause()

        strips = app.screen._compositor.render_strips()
        search_text = "\n".join(strip.text for strip in strips)
        assert len(strips) == height
        assert all(len(strip.text) <= width for strip in strips)
        assert "MEMORIES / SEARCH" in search_text
        assert app.query_one(MemoriesSurface).display
        assert not app.query_one(HomeSurface).display
        assert not runtime.started
        assert "TASKS" not in search_text
        assert "FORMAT" not in search_text


async def test_home_status_is_read_only_and_updates_details(tmp_path: Path) -> None:
    app, diagnostics, _search, runtime = _app(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert diagnostics.calls == 1
        assert not runtime.started
        assert app.query_one(HomeSurface).display
        assert app.query_one(HomeDetailsSurface).display
        assert not app.query_one(MemoriesSurface).display
        assert "READY" in str(app.query_one("#home-readiness", Static).render())
        detail = str(app.query_one("#home-detail-content", Static).render())
        assert str(app.paths.config_path) in detail
        assert "Missing tables: -" in detail
        assert "Missing indexes: -" in detail
        assert "Pending migrations: -" in detail
        assert "storage backend: sqlite" in detail
        assert "default Top K: 10" in detail
        assert "RRF k: 60" in detail
        assert "tokenizer: unicode61" in detail
        assert "scheduler enabled: true" in detail
        assert "health watchdog enabled: false" in detail
        warning_text = "\n".join(
            str(widget.render()) for widget in app.query_one("#home-warning-list").query(Static)
        )
        assert "diagnostics.scheduler_inactive" in warning_text


async def test_search_disclosure_consent_results_details_and_non_cancellable_lifecycle(
    tmp_path: Path,
) -> None:
    app, _diagnostics, search, _runtime = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#route-memories")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        assert app.state.route_id == "memories"
        assert surface.display
        assert not app.query_one(HomeSurface).display

        notice = surface.query_one("#search-runtime-notice", NoticeBlock)
        assert notice.has_class("notice-warning")
        button = surface.query_one("#search-submit", PanelButton)
        assert str(button.label) == "INITIALIZE & SEARCH"
        assert not surface.query("#search-cancel")
        assert not surface.query(".task-center")

        query = surface.query_one("#search-query", TuiInput)
        query.value = "memory query"
        surface.query_one("#search-source", TuiInput).value = " source with spaces "
        top_k = surface.query_one("#search-top-k", TuiInput)
        top_k.value = "not-[private]"
        await surface.start_search()
        error_text = "\n".join(
            str(widget.render()) for widget in surface.query_one("#search-error-host").query(Static)
        )
        assert "Top K must be an integer." in error_text
        assert "not-[private]" not in error_text
        assert search.requests == []

        top_k.value = "10"
        button.scroll_visible(animate=False, immediate=True, top=True)
        await pilot.pause()
        await pilot.click("#search-submit")
        await pilot.pause()
        await pilot.pause()

        assert len(search.requests) == 1
        request = search.requests[0]
        assert request.allow_runtime_initialization is True
        assert request.top_k == 10
        assert request.source_filter == " source with spaces "
        operation = surface.query_one("#search-operation-state", OperationStateBlock)
        assert operation.has_class("state-succeeded")
        view = surface.query_one("#search-results", TableView)
        assert view.table.row_count == 2
        assert str(view.table.get_cell_at(Coordinate(0, 3))) == "first full [literal] content"
        assert str(button.label) == "SEARCH"
        app.refresh(layout=True)
        await pilot.pause()
        composited = "\n".join(strip.text for strip in app.screen._compositor.render_strips())
        assert "Results 2" in composited
        assert "RANK" in composited

        details = app.query_one(MemoryDetailsSurface)
        assert details.selected_item is not None
        assert details.selected_item.chunk_id == "first[1]"
        rendered = "\n".join(str(widget.render()) for widget in details.query(Static))
        assert "first full [literal] content" in rendered

        await pilot.press("f4")
        assert app.state.active_section == "detail"
        await pilot.press("left_square_bracket")
        assert app.state.active_section == "main"


async def test_search_uses_configured_default_top_k_and_preserves_user_override(
    tmp_path: Path,
) -> None:
    app, _diagnostics, search, _runtime = _app(tmp_path, default_top_k=37)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.click("#route-memories")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        top_k = surface.query_one("#search-top-k", TuiInput)

        assert top_k.value == "37"
        supporting_text = "\n".join(
            str(widget.render()) for widget in surface.query(".form-support")
        )
        assert "Configured memtomem default: 37." in supporting_text

        top_k.value = "6"
        surface.refresh_preflight()
        assert top_k.value == "6"

        top_k.value = "37"
        surface.query_one("#search-query", TuiInput).value = "configured default"
        await surface.start_search()
        await pilot.pause()
        await pilot.pause()

        assert search.requests[-1].top_k == 37


async def test_search_setup_required_is_actionable_without_starting_runtime(
    tmp_path: Path,
) -> None:
    app, _diagnostics, search, runtime = _app(tmp_path, setup_required=True)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.click("#route-memories")
        surface = app.query_one(MemoriesSurface)
        notice = surface.query_one("#search-runtime-notice", NoticeBlock)
        button = surface.query_one("#search-submit", PanelButton)

        assert notice.has_class("notice-warning")
        assert "SETUP REQUIRED" in str(notice.query_one(".notice-title", Static).render())
        assert str(button.label) == "SETUP REQUIRED"
        assert button.disabled
        assert search.requests == []
        assert not runtime.started


async def test_search_config_error_is_visible_and_blocks_runtime_action(
    tmp_path: Path,
) -> None:
    error = UserSafeError(
        code="search.config-unreadable",
        message="Search cannot start because configuration could not be read safely.",
        recovery_action="Review config.json and config.d before trying again.",
        retryable=True,
    )
    app, _diagnostics, search, runtime = _app(tmp_path, readiness_error=error)

    async with app.run_test(size=(48, 12)) as pilot:
        await pilot.click("#route-memories")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        notice = surface.query_one("#search-runtime-notice", NoticeBlock)
        button = surface.query_one("#search-submit", PanelButton)
        rendered = "\n".join(str(widget.render()) for widget in notice.query(Static))

        assert "CONFIGURATION UNREADABLE" in rendered
        assert "Review config.json and config.d" in rendered
        assert notice.has_class("notice-error")
        assert button.disabled
        assert str(button.label) == "CONFIG ERROR"
        await surface.start_search()
        assert search.requests == []
        assert not runtime.started


async def test_route_resize_and_mouse_preserve_search_form_results_and_selection(
    tmp_path: Path,
) -> None:
    app, _diagnostics, _search, _runtime = _app(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.click("#route-memories")
        surface = app.query_one(MemoriesSurface)
        query = surface.query_one("#search-query", TuiInput)
        query.value = "preserve [query]"
        await surface.start_search()
        await pilot.pause()
        view = surface.query_one("#search-results", TableView)
        view.table.move_cursor(row=1, column=0, animate=False)
        await pilot.pause()
        assert app.query_one(MemoryDetailsSurface).selected_item is not None
        assert app.query_one(MemoryDetailsSurface).selected_item.chunk_id == "second[2]"

        await pilot.resize_terminal(48, 12)
        assert query.value == "preserve [query]"
        assert view.table.row_count == 2
        assert app.state.route_id == "memories"

        await pilot.press("f2")
        await pilot.click("#route-home")
        await pilot.click("#route-memories")
        assert query.value == "preserve [query]"
        assert view.table.row_count == 2
        assert app.query_one(MemoryDetailsSurface).selected_item.chunk_id == "second[2]"

        await pilot.press("f4")
        assert app.state.active_section == "detail"
        await pilot.resize_terminal(120, 30)
        surface.scroll_to_widget(
            view.table,
            animate=False,
            immediate=True,
            force=True,
            top=True,
        )
        await pilot.pause()
        await pilot.click("#search-results DataTable")
        assert app.state.active_section == "main"


async def test_partial_search_keeps_results_and_renders_structured_warning(
    tmp_path: Path,
) -> None:
    warning = UserSafeWarning(
        code="search.reranker-degraded",
        message="Reranking failed; results remain in their pre-rerank order.",
        recovery_action="Review reranker readiness before retrying.",
    )
    app, _diagnostics, _search, _runtime = _app(
        tmp_path,
        result=OperationResult.partial(_response(), warnings=(warning,)),
    )
    async with app.run_test(size=(48, 12)) as pilot:
        app.state.route_id = "memories"
        app._update_route_classes()
        app.activate_section("main")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        surface.query_one("#search-query", TuiInput).value = "degraded"
        await surface.start_search()
        await pilot.pause()

        assert surface.query_one("#search-operation-state", OperationStateBlock).has_class(
            "state-partial"
        )
        assert surface.query_one("#search-results", TableView).table.row_count == 2
        warnings = surface.query_one("#search-warning-list")
        assert warnings.display
        rendered = "\n".join(str(widget.render()) for widget in warnings.query(Static))
        assert "search.reranker-degraded" in rendered
        assert "pre-rerank order" in rendered
        composited = "\n".join(strip.text for strip in app.screen._compositor.render_strips())
        assert "search.reranker-degraded" in composited


async def test_failed_search_renders_safe_error_and_clears_result_details(
    tmp_path: Path,
) -> None:
    failure = UserSafeError(
        code="search.retrieval-failed",
        message="Every enabled search retrieval method failed.",
        recovery_action="Review Search readiness and try again.",
        retryable=True,
    )
    app, _diagnostics, _search, _runtime = _app(
        tmp_path,
        result=OperationResult.failed(failure),
    )
    async with app.run_test(size=(48, 12)) as pilot:
        app.state.route_id = "memories"
        app._update_route_classes()
        app.activate_section("main")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        surface.query_one("#search-query", TuiInput).value = "failure"
        await surface.start_search()
        await pilot.pause()

        assert surface.query_one("#search-operation-state", OperationStateBlock).has_class(
            "state-failed"
        )
        assert surface.query_one("#search-results", TableView).table.row_count == 0
        error_host = surface.query_one("#search-error-host")
        rendered = "\n".join(str(widget.render()) for widget in error_host.query(Static))
        assert "search.retrieval-failed" in rendered
        assert "Every enabled search retrieval method failed." in rendered
        assert app.query_one(MemoryDetailsSurface).selected_item is None
        composited = "\n".join(strip.text for strip in app.screen._compositor.render_strips())
        assert "search.retrieval-failed" in composited


async def test_compact_reveal_discards_stale_post_refresh_scroll(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _diagnostics, _search, _runtime = _app(tmp_path)
    scheduled: list[tuple[object, tuple[object, ...]]] = []
    revealed: list[str | None] = []

    async with app.run_test(size=(48, 12)) as pilot:
        await pilot.click("#route-memories")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        operation = surface.query_one("#search-operation-state")
        error_host = surface.query_one("#search-error-host")

        def schedule(_self, callback, *args, **_kwargs) -> bool:
            scheduled.append((callback, args))
            return True

        def record_scroll(_self, widget, **_kwargs) -> None:
            revealed.append(widget.id)

        monkeypatch.setattr(MemoriesSurface, "call_after_refresh", schedule)
        monkeypatch.setattr(MemoriesSurface, "scroll_to_widget", record_scroll)

        surface._reveal(operation)
        surface._reveal(error_host)
        for callback, args in scheduled:
            callback(*args)  # type: ignore[operator]

        assert revealed == ["search-error-host"]


async def test_successful_empty_search_renders_explicit_no_matches_state(
    tmp_path: Path,
) -> None:
    response = SearchResponse(
        query="no matches",
        items=(),
        stats=SearchStats(0, 0, 0, 0, 0, 20, 15),
        project_context_root=None,
    )
    app, _diagnostics, _search, _runtime = _app(
        tmp_path,
        result=OperationResult.succeeded(response),
    )
    async with app.run_test(size=(48, 12)) as pilot:
        app.state.route_id = "memories"
        app._update_route_classes()
        app.activate_section("main")
        await pilot.pause()
        surface = app.query_one(MemoriesSurface)
        surface.query_one("#search-query", TuiInput).value = "no matches"
        await surface.start_search()
        await pilot.pause()

        view = surface.query_one("#search-results", TableView)
        assert view.table.row_count == 0
        empty_text = "\n".join(str(widget.render()) for widget in view.query(Static))
        assert "NO MATCHES" in empty_text
        assert "current query and filters" in empty_text
        composited = "\n".join(strip.text for strip in app.screen._compositor.render_strips())
        assert "NO MATCHES" in composited
