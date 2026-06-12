"""Command catalog used to track CLI-to-TUI parity."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TuiSupport(str, Enum):
    NATIVE = "native"
    PALETTE = "palette"
    PLANNED = "planned"
    DANGEROUS = "dangerous"


@dataclass(frozen=True)
class CommandEntry:
    command: str
    title: str
    support: TuiSupport
    notes: str


COMMAND_CATALOG: tuple[CommandEntry, ...] = (
    CommandEntry("mm init", "Setup wizard", TuiSupport.PLANNED, "Startup routes here first."),
    CommandEntry("mm index", "Index files", TuiSupport.NATIVE, "Startup offers this when needed."),
    CommandEntry("mm mem", "Memory audit", TuiSupport.PLANNED, "Native audit views."),
    CommandEntry("mm status", "Status", TuiSupport.NATIVE, "Dashboard summary."),
    CommandEntry("mm search", "Search", TuiSupport.PLANNED, "Native search screen next."),
    CommandEntry("mm add", "Add memory", TuiSupport.PLANNED, "Needs shared add action."),
    CommandEntry("mm recall", "Recall", TuiSupport.PLANNED, "Timeline/recent memory screen."),
    CommandEntry("mm tags", "Tags", TuiSupport.PLANNED, "Native tag management."),
    CommandEntry("mm config", "Config", TuiSupport.PLANNED, "Typed settings forms."),
    CommandEntry(
        "mm embedding-reset",
        "Embedding reset",
        TuiSupport.DANGEROUS,
        "Preview and confirm vector reset.",
    ),
    CommandEntry("mm context", "Context", TuiSupport.PALETTE, "Large workflow, screen by screen."),
    CommandEntry("mm agent", "Agent memory", TuiSupport.PALETTE, "Command palette first."),
    CommandEntry("mm session", "Sessions", TuiSupport.PALETTE, "Native views later."),
    CommandEntry("mm activity", "Activity", TuiSupport.PALETTE, "Command palette first."),
    CommandEntry("mm schedule", "Schedule", TuiSupport.PALETTE, "Native rows/actions later."),
    CommandEntry("mm watchdog", "Watchdog", TuiSupport.PALETTE, "Health panel later."),
    CommandEntry("mm memory doctor", "Memory doctor", TuiSupport.PLANNED, "Native report view."),
    CommandEntry("mm ingest", "Ingest", TuiSupport.PALETTE, "Wizard later."),
    CommandEntry("mm wiki", "Wiki", TuiSupport.PALETTE, "Command palette first."),
    CommandEntry("mm web", "Web UI", TuiSupport.PALETTE, "Launch/status actions."),
    CommandEntry("mm shell", "Interactive shell", TuiSupport.PALETTE, "Legacy shell remains available."),
    CommandEntry("mm sync-doctor", "Sync doctor", TuiSupport.PLANNED, "Native diagnostic view."),
    CommandEntry("mm version", "Version", TuiSupport.NATIVE, "About panel."),
    CommandEntry("mm gc", "Garbage collection", TuiSupport.DANGEROUS, "Preview and confirm."),
    CommandEntry("mm purge", "Purge", TuiSupport.DANGEROUS, "Preview and confirm."),
    CommandEntry("mm reset", "Reset", TuiSupport.DANGEROUS, "Strong confirmation required."),
    CommandEntry("mm uninstall", "Uninstall", TuiSupport.DANGEROUS, "Strong confirmation required."),
    CommandEntry("mm upgrade", "Upgrade", TuiSupport.DANGEROUS, "External package operation."),
)
