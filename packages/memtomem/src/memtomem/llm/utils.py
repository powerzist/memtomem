"""Shared helpers for parsing LLM responses."""

from __future__ import annotations


def strip_llm_response(raw: str) -> str:
    """Strip markdown code fences and surrounding whitespace from LLM output.

    Small models often wrap their output in ````...```` blocks (sometimes
    with a language tag).  This helper peels that wrapper so downstream
    parsers see only the payload.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```lang) and last line (```)
        if lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
        else:
            text = "\n".join(lines[1:]).strip()
    return text
