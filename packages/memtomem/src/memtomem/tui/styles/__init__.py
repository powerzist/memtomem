"""Load the logically layered Phase 2 stylesheet in token-sharing order."""

from pathlib import Path


STYLE_FILES = (
    "tokens.tcss",
    "layout.tcss",
    "components.tcss",
    "states.tcss",
    "responsive.tcss",
)


def load_tui_css() -> str:
    """Join layers because Textual parses variables per physical CSS path."""
    root = Path(__file__).parent
    return "\n".join((root / name).read_text(encoding="utf-8") for name in STYLE_FILES)
