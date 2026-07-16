"""Focused contracts for the public ``mm tui --diagnose-input`` surface."""

from __future__ import annotations

from textual import events
from textual.widgets import Static

from memtomem.tui.screens.diagnostics import DiagnosticInput, InputDiagnosticsApp


def test_input_diagnostics_detects_terminal_profile_when_not_supplied(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "memtomem.tui.screens.diagnostics.detect_terminal_profile",
        lambda: "windows-terminal",
    )

    app = InputDiagnosticsApp()

    assert app.terminal_profile == "windows-terminal"


async def test_input_diagnostics_warns_about_conhost_ime_limitations() -> None:
    app = InputDiagnosticsApp(terminal_profile="windows-conhost")

    async with app.run_test() as pilot:
        await pilot.pause()

        warnings = [
            str(widget.content) for widget in app.query("#diagnostics .warning").results(Static)
        ]
        assert any("Korean IME input is limited" in warning for warning in warnings)
        assert isinstance(app.focused, DiagnosticInput)


async def test_input_diagnostics_records_key_and_paste_events_with_current_value() -> None:
    app = InputDiagnosticsApp(terminal_profile="windows-terminal")

    async with app.run_test() as pilot:
        field = app.query_one("#diagnostics-input", DiagnosticInput)
        await pilot.press("a")
        field.post_message(events.Paste("붙여넣기"))
        await pilot.pause()

        assert field.value == "a붙여넣기"
        log_text = str(app.query_one("#diagnostics-log-text", Static).content)
        assert "001 key:" in log_text
        assert "key='a'" in log_text
        assert "character='a'" in log_text
        assert "value_before=''" in log_text
        assert "002 paste:" in log_text
        assert "text='붙여넣기'" in log_text
        assert "value_before='a'" in log_text
        assert str(app.query_one("#diagnostics-value", Static).content) == (
            "Current value: 'a붙여넣기'"
        )


async def test_input_diagnostics_renders_bracketed_input_literally() -> None:
    app = InputDiagnosticsApp(terminal_profile="windows-terminal")
    payload = "[x][bold][/]"

    async with app.run_test(size=(100, 24)) as pilot:
        field = app.query_one("#diagnostics-input", DiagnosticInput)
        field.post_message(events.Paste(payload))
        await pilot.pause()

        value = app.query_one("#diagnostics-value", Static)
        log = app.query_one("#diagnostics-log-text", Static)
        rendered_value = "\n".join(
            value.render_line(row).text for row in range(value.region.height)
        )
        rendered_log = "\n".join(log.render_line(row).text for row in range(log.region.height))

        assert payload in rendered_value
        assert payload in rendered_log


async def test_input_diagnostics_keeps_only_the_latest_forty_events() -> None:
    app = InputDiagnosticsApp(terminal_profile="windows-terminal")

    async with app.run_test() as pilot:
        for _ in range(45):
            await pilot.press("a")
        await pilot.pause()

        assert len(app.input_events) == 40
        assert app.input_events[0].startswith("006 key:")
        assert app.input_events[-1].startswith("045 key:")
