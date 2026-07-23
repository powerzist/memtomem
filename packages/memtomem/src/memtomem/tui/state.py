"""Session-scoped state for the modular Textual shell."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LayoutMode(str, Enum):
    """Responsive layouts derived from the rebuild contract."""

    WIDE = "wide"
    STANDARD = "standard"
    COMPACT = "compact"
    EXTREME = "extreme"
    SAFE_FLOOR = "safe-floor"

    @classmethod
    def from_viewport(cls, width: int, height: int) -> LayoutMode:
        if width < 32 or height < 8:
            return cls.SAFE_FLOOR
        if width <= 40 or height <= 10:
            return cls.EXTREME
        if width < 60 or height < 16:
            return cls.COMPACT
        if width < 100:
            return cls.STANDARD
        return cls.WIDE


@dataclass(frozen=True)
class Route:
    """A shell destination, independent from Click commands."""

    id: str
    label: str
    short_label: str
    available: bool = False


ROUTES = (
    Route("home", "Home", "Home", available=True),
    Route("memories", "Memories", "Memory", available=True),
    Route("sources", "Sources", "Sources"),
    Route("context", "Context", "Context"),
    Route("collaboration", "Agents & Sessions", "Agents"),
    Route("automation", "Automation", "Auto"),
    Route("wiki", "Wiki", "Wiki"),
    Route("settings", "Settings", "Settings"),
    Route("maintenance", "Maintenance", "Maintain"),
    Route("services", "Services", "Services"),
)


@dataclass
class ErrorNotice:
    """Structured, user-safe error displayed by the global shell."""

    code: str
    message: str
    detail: str | None = None
    recoverable: bool = False


@dataclass
class ShellState:
    """State that must survive route changes and responsive recomposition."""

    route_id: str = "home"
    active_section: str = "nav"
    layout_mode: LayoutMode = LayoutMode.WIDE
    remembered_focus: dict[str, str | None] = field(
        default_factory=lambda: {
            "nav": "route-home",
            "main": "home-surface",
            "detail": "details-surface",
        }
    )
    error: ErrorNotice | None = None

    def activate(self, section: str) -> None:
        if section not in {"nav", "main", "detail"}:
            raise ValueError(f"unknown shell section: {section}")
        self.active_section = section
