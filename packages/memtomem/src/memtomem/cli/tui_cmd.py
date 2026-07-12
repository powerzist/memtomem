"""CLI: mm tui -- launch the Textual terminal UI."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import click


def _tui_install_hint() -> str:
    return 'uv tool install --reinstall "memtomem[tui]"'


def _check_tui_deps() -> None:
    from importlib.util import find_spec

    if find_spec("textual") is not None:
        return
    click.secho("Error: TUI requires the [tui] extra (missing: textual).", fg="red")
    click.echo("The base install does not include Textual dependencies.")
    click.echo("To add them, reinstall with the [tui] extra:")
    click.echo(f"  {_tui_install_hint()}")
    click.echo('  Or, from source: uv pip install -e "packages/memtomem[tui]"')
    raise SystemExit(1)


@click.command("tui")
@click.option(
    "--dev",
    is_flag=True,
    help="Use project-local TUI state under .dev/.memtomem.",
)
@click.option(
    "--border",
    "border_mode",
    type=click.Choice(("auto", "solid", "ascii"), case_sensitive=False),
    default="auto",
    show_default=True,
    help="Border rendering mode. Use ascii for legacy Windows consoles.",
)
@click.option(
    "--diagnose-terminal",
    is_flag=True,
    help="Print terminal detection details and border samples, then exit.",
)
@click.option(
    "--diagnose-input",
    is_flag=True,
    help="Open a Textual input diagnostics screen for IME and paste troubleshooting.",
)
@click.option(
    "--mouse/--no-mouse",
    default=True,
    show_default=True,
    help="Enable or disable terminal mouse tracking.",
)
def tui(
    border_mode: str,
    dev: bool,
    diagnose_terminal: bool,
    diagnose_input: bool,
    mouse: bool,
) -> None:
    """Launch the memtomem terminal UI."""
    from memtomem.tui.terminal import (
        BorderMode,
        choose_border_style,
        detect_terminal_profile,
        terminal_diagnostics,
    )

    normalized_border_mode = cast(BorderMode, border_mode.lower())

    if diagnose_terminal:
        click.echo(terminal_diagnostics(normalized_border_mode))
        return

    _check_tui_deps()
    from memtomem.tui.app import run, run_input_diagnostics
    from memtomem.tui.runtime import resolve_tui_paths

    border_style = choose_border_style(normalized_border_mode)
    terminal_profile = detect_terminal_profile()
    if diagnose_input:
        run_input_diagnostics(
            border_style=border_style,
            mouse=mouse,
            terminal_profile=terminal_profile,
        )
        return

    kwargs = {
        "border_style": border_style,
        "mouse": mouse,
        "terminal_profile": terminal_profile,
    }
    if dev:
        try:
            kwargs["paths"] = resolve_tui_paths(dev=True, cwd=Path.cwd())
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
    run(**kwargs)
