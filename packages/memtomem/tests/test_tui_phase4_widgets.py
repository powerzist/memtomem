"""Phase 4 tests for dynamic, reusable Search and status presenters."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.coordinate import Coordinate
from textual.widgets import Static

from memtomem.tui.application.contracts import OperationStatus
from memtomem.tui.application.search import (
    SearchContextChunk,
    SearchContextDetail,
    SearchResponse,
    SearchResultItem,
    SearchStats,
)
from memtomem.tui.screens.memories import MemoryDetailsSurface
from memtomem.tui.styles import load_tui_css
from memtomem.tui.widgets.operation_status import (
    OperationStateBlock,
    OperationStatePresentation,
)
from memtomem.tui.widgets.preview import EmptyState, NoticeBlock
from memtomem.tui.widgets.tables import TableColumn, TableRow, TableView


def _item(
    *, chunk_id: str = "chunk[1]", content: str = "full\n[literal]\ncontent"
) -> SearchResultItem:
    adjacent = SearchContextChunk(
        chunk_id="before[0]",
        source_file="C:/memory/[before].md",
        content="adjacent [literal] content",
        heading_hierarchy=("Parent", "Before"),
        start_line=1,
        end_line=4,
    )
    return SearchResultItem(
        chunk_id=chunk_id,
        rank=1,
        score=0.987654,
        retrieval_source="hybrid",
        source_file="C:/memory/[one].md",
        content=content,
        heading_hierarchy=("Root", "Child [one]"),
        chunk_type="section",
        start_line=5,
        end_line=12,
        language="en",
        tags=("alpha", "beta[2]"),
        namespace="project[test]",
        scope="project_local",
        project_root="C:/project/[root]",
        valid_from_unix=100,
        valid_to_unix=200,
        created_at=datetime(2026, 7, 18, 1, 2, tzinfo=UTC),
        updated_at=datetime(2026, 7, 18, 3, 4, tzinfo=UTC),
        via_session_summary=False,
        context=SearchContextDetail(
            window_before=(adjacent,),
            window_after=(),
            parent_content="parent [literal] content",
            parent_heading="Parent [heading]",
            sibling_count=3,
            chunk_position=2,
            total_chunks_in_file=5,
            context_tier_used="section",
        ),
    )


def _response(item: SearchResultItem) -> SearchResponse:
    return SearchResponse(
        query="literal [query]",
        items=(item,),
        stats=SearchStats(
            bm25_candidates=5,
            dense_candidates=4,
            fused_total=6,
            final_total=1,
            hidden_system_namespaces=0,
            indexed_chunks=10,
            dense_chunks=8,
        ),
        project_context_root="C:/project/[root]",
    )


class _DynamicWidgetsApp(App[None]):
    CSS = load_tui_css()

    def compose(self) -> ComposeResult:
        yield NoticeBlock(
            "DISCLOSURE",
            "No mutation yet.",
            tone="warning",
            id="notice",
        )
        yield OperationStateBlock(
            OperationStatePresentation(OperationStatus.QUEUED, "Queued"),
            id="operation",
        )
        yield TableView(
            (TableColumn("value", "VALUE"),),
            empty_title="EMPTY",
            empty_message="No rows.",
            id="table-view",
        )


async def test_dynamic_presenters_update_without_replacing_stable_controls() -> None:
    app = _DynamicWidgetsApp()
    async with app.run_test(size=(80, 24)):
        view = app.query_one("#table-view", TableView)
        table = view.table
        assert not table.display
        assert view.query_one(EmptyState).display

        view.replace_rows((TableRow(("value[1]",), key="row[1]"),))
        assert view.table is table
        assert table.display
        assert not view.query_one(EmptyState).display
        assert str(table.get_cell_at(Coordinate(0, 0))) == "value[1]"

        operation = app.query_one("#operation", OperationStateBlock)
        operation.update_presentation(
            OperationStatePresentation(
                OperationStatus.PARTIAL,
                "Completed with a degraded retriever.",
                completed=1,
                remaining=0,
                recovery="Review the warning.",
            )
        )
        assert operation.has_class("state-partial")
        rendered = "\n".join(str(widget.render()) for widget in operation.query(Static))
        assert "PARTIAL" in rendered
        assert "Completed 1" in rendered
        assert "Review the warning." in rendered

        notice = app.query_one("#notice", NoticeBlock)
        notice.update_notice("RUNTIME READY", "Search runtime is active.", tone="ok")
        assert notice.has_class("notice-ok")
        assert "[+] RUNTIME READY" in str(notice.query_one(".notice-title", Static).render())


async def test_search_details_preserve_full_literal_content_metadata_and_context() -> None:
    item = _item()
    response = _response(item)

    class _DetailsApp(App[None]):
        CSS = load_tui_css()

        def compose(self) -> ComposeResult:
            yield MemoryDetailsSurface()

    app = _DetailsApp()
    async with app.run_test(size=(60, 24)):
        details = app.query_one(MemoryDetailsSurface)
        await details.show_item(item, response)
        rendered = "\n".join(str(widget.render()) for widget in details.query(Static))

        assert "full\n[literal]\ncontent" in rendered
        assert "C:/memory/[one].md" in rendered
        assert "project[test]" in rendered
        assert "parent [literal] content" in rendered
        assert "adjacent [literal] content" in rendered
        assert "BM25 5" in rendered


def test_phase4_css_uses_semantic_families_without_feature_control_id_rules() -> None:
    styles = Path(__file__).parents[1] / "src" / "memtomem" / "tui" / "styles"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in styles.glob("*.tcss"))

    for semantic_class in (
        ".route-surface",
        ".notice-block",
        ".status-row",
        ".filter-grid",
        ".result-table-view",
        ".memory-content",
    ):
        assert semantic_class in combined

    for control_id in (
        "#home-refresh",
        "#search-submit",
        "#search-query",
        "#search-results",
        "#memory-detail-body",
    ):
        assert control_id not in combined
