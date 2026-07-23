"""Strictly read-only Home and Status presentation."""

from __future__ import annotations

import asyncio
from functools import partial

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Static

from memtomem.tui.application.diagnostics import (
    DatabaseState,
    DiagnosticsSnapshot,
    ReadOnlyDiagnosticsService,
    SchemaState,
    SetupState,
)
from memtomem.tui.widgets.controls import PanelButton
from memtomem.tui.widgets.forms import ActionBar
from memtomem.tui.widgets.preview import NoticeBlock


def _display_count(value: int | None) -> str:
    return "-" if value is None else str(value)


class StatusRow(Vertical):
    """Compact label/value/note row shared by Home diagnostic facts."""

    def __init__(self, label: str, value: str, note: str, *, tone: str = "muted") -> None:
        super().__init__(classes=f"status-row status-{tone}")
        self.label = label
        self.value = value
        self.note = note

    def compose(self) -> ComposeResult:
        yield Static(self.label, classes="status-label", markup=False)
        yield Static(self.value, classes="status-value", markup=False)
        yield Static(self.note, classes="status-note muted", markup=False)


class HomeSurface(VerticalScroll, can_focus=True):
    """Read-only diagnostics that never acquires a mutable runtime lease."""

    class DiagnosticsUpdated(Message):
        def __init__(self, snapshot: DiagnosticsSnapshot) -> None:
            super().__init__()
            self.snapshot = snapshot

    def __init__(
        self,
        diagnostics: ReadOnlyDiagnosticsService,
        *,
        auto_refresh: bool = True,
    ) -> None:
        super().__init__(id="home-surface", classes="route-surface home-surface")
        self.diagnostics = diagnostics
        self.startup_inspection = auto_refresh
        self.snapshot: DiagnosticsSnapshot | None = None

    def compose(self) -> ComposeResult:
        yield Static("[ HOME / STATUS ]", classes="section-title", markup=False)
        yield NoticeBlock(
            "READ-ONLY DIAGNOSTICS",
            "Home inspects configuration and storage without creating a database, "
            "running migrations, indexing files, or building embeddings.",
            tone="ok",
            classes="inline-notice",
        )
        yield Static(
            "[ ] NOT INSPECTED",
            classes="readiness-line muted",
            id="home-readiness",
            markup=False,
        )
        yield Vertical(id="home-status-rows", classes="status-list")
        yield Vertical(id="home-warning-list", classes="notice-stack")
        yield ActionBar(
            PanelButton(
                "REFRESH STATUS",
                id="home-refresh",
                classes="action-button cyan",
            )
        )

    def on_mount(self) -> None:
        if self.startup_inspection:
            self.refresh_diagnostics()

    def on_button_pressed(self, event: PanelButton.Pressed) -> None:
        if event.button.id == "home-refresh":
            self.refresh_diagnostics()

    def refresh_diagnostics(self) -> None:
        """Schedule one read-only observation while keeping this surface mounted."""
        button = self.query_one("#home-refresh", PanelButton)
        button.disabled = True
        readiness = self.query_one("#home-readiness", Static)
        readiness.update("[...] INSPECTING READ-ONLY STATE")
        readiness.set_classes("readiness-line muted")
        self.run_worker(
            partial(self._inspect),  # type: ignore[arg-type]
            group="home-read-only-diagnostics",
            exclusive=True,
        )

    async def _inspect(self) -> None:
        try:
            snapshot = await self.diagnostics.inspect()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._show_inspection_failure()
            return
        finally:
            try:
                self.query_one("#home-refresh", PanelButton).disabled = False
            except NoMatches:
                pass
        self.snapshot = snapshot
        await self._show_snapshot(snapshot)
        self.post_message(self.DiagnosticsUpdated(snapshot))

    async def _show_snapshot(self, snapshot: DiagnosticsSnapshot) -> None:
        readiness = self.query_one("#home-readiness", Static)
        tone = "ok"
        if snapshot.setup.state is SetupState.ERROR:
            label = "[x] CONFIGURATION ERROR"
            tone = "error"
        elif snapshot.setup.state is SetupState.REQUIRED:
            label = "[!] SETUP REQUIRED"
            tone = "warning"
        elif snapshot.database.state is DatabaseState.UNREADABLE:
            label = "[x] DATABASE UNREADABLE"
            tone = "error"
        elif snapshot.schema.state is SchemaState.MIGRATION_REQUIRED:
            label = "[!] SEARCH INITIALIZATION REQUIRED"
            tone = "warning"
        elif snapshot.database.state is DatabaseState.MISSING:
            label = "[!] SEARCH DATABASE MISSING"
            tone = "warning"
        elif snapshot.schema.state is SchemaState.READY:
            label = "[+] READY"
        else:
            label = "[-] STATUS LIMITED"
            tone = "muted"
        readiness.update(label)
        readiness.set_classes(f"readiness-line {tone}")

        dense = snapshot.dense_coverage
        dense_value = "-"
        dense_note = "Coverage unavailable"
        if dense is not None:
            dense_value = f"{dense.with_dense}/{dense.total}"
            dense_note = (
                "No indexed chunks"
                if dense.ratio is None
                else f"{dense.ratio * 100:.1f}% dense coverage"
            )
        rows = (
            StatusRow("Setup", snapshot.setup.state.value, str(snapshot.setup.config_path)),
            StatusRow("Database", snapshot.database.state.value, str(snapshot.database.path)),
            StatusRow("Storage", snapshot.storage_backend, "Configured storage backend"),
            StatusRow(
                "Schema",
                snapshot.schema.state.value,
                "No migration is run from Home",
                tone=(
                    "warning"
                    if snapshot.schema.state is SchemaState.MIGRATION_REQUIRED
                    else "muted"
                ),
            ),
            StatusRow("Chunks", _display_count(snapshot.chunks), "Indexed chunk rows"),
            StatusRow("Sources", _display_count(snapshot.sources), "Distinct source paths"),
            StatusRow("Dense", dense_value, dense_note),
            StatusRow(
                "Search",
                f"Top K {snapshot.default_top_k} / RRF k {snapshot.rrf_k}",
                f"Tokenizer {snapshot.tokenizer}",
            ),
            StatusRow(
                "Automation",
                f"Scheduler {'on' if snapshot.scheduler_enabled else 'off'}",
                f"Health watchdog {'on' if snapshot.health_watchdog_enabled else 'off'}",
                tone=(
                    "warning"
                    if snapshot.scheduler_enabled and not snapshot.health_watchdog_enabled
                    else "muted"
                ),
            ),
        )
        status_rows = self.query_one("#home-status-rows", Vertical)
        await status_rows.remove_children()
        await status_rows.mount(*rows)

        warnings = self.query_one("#home-warning-list", Vertical)
        await warnings.remove_children()
        await warnings.mount(
            *(
                NoticeBlock(
                    warning.code,
                    warning.message,
                    tone="warning",
                    recovery=warning.recovery_action,
                )
                for warning in snapshot.warnings
            )
        )
        warnings.display = bool(snapshot.warnings)

    def _show_inspection_failure(self) -> None:
        readiness = self.query_one("#home-readiness", Static)
        readiness.update("[x] READ-ONLY INSPECTION FAILED")
        readiness.set_classes("readiness-line error")


class HomeDetailsSurface(VerticalScroll, can_focus=True):
    """Read-mostly provenance and embedding details for the Home snapshot."""

    def __init__(self) -> None:
        super().__init__(id="home-details-surface", classes="route-surface details-surface")
        self.snapshot: DiagnosticsSnapshot | None = None

    def compose(self) -> ComposeResult:
        yield Static("[ HOME DETAILS ]", classes="section-title", markup=False)
        yield Static(
            "Refresh Home to inspect configuration paths, schema gaps, and embedding metadata.",
            id="home-detail-content",
            classes="detail-copy muted",
            markup=False,
        )

    def show_snapshot(self, snapshot: DiagnosticsSnapshot) -> None:
        self.snapshot = snapshot
        embedding = snapshot.embedding
        lines = [
            f"Config: {snapshot.setup.config_path}",
            f"Database: {snapshot.database.path}",
            "Memory roots:",
            *(f"  - {path}" for path in snapshot.setup.memory_dirs),
            "",
            f"Missing tables: {', '.join(snapshot.schema.missing_tables) or '-'}",
            f"Missing columns: {', '.join(snapshot.schema.missing_columns) or '-'}",
            f"Missing indexes: {', '.join(snapshot.schema.missing_indexes) or '-'}",
            f"Pending migrations: {', '.join(snapshot.schema.pending_migrations) or '-'}",
            f"Orphan source paths: {_display_count(snapshot.orphans)}",
            "",
            "Status configuration:",
            f"  storage backend: {snapshot.storage_backend}",
            f"  default Top K: {snapshot.default_top_k}",
            f"  RRF k: {snapshot.rrf_k}",
            f"  tokenizer: {snapshot.tokenizer}",
            f"  scheduler enabled: {str(snapshot.scheduler_enabled).lower()}",
            f"  health watchdog enabled: {str(snapshot.health_watchdog_enabled).lower()}",
        ]
        if embedding is not None:
            lines.extend(
                (
                    "",
                    "Embedding configuration:",
                    f"  configured: {embedding.configured_provider} / "
                    f"{embedding.configured_model} / {embedding.configured_dimension}",
                    f"  stored: {embedding.stored_provider or '-'} / "
                    f"{embedding.stored_model or '-'} / "
                    f"{embedding.stored_dimension if embedding.stored_dimension is not None else '-'}",
                    f"  mismatch: {'yes' if embedding.mismatch else 'no'}",
                )
            )
        self.query_one("#home-detail-content", Static).update("\n".join(lines))


__all__ = ["HomeDetailsSurface", "HomeSurface", "StatusRow"]
