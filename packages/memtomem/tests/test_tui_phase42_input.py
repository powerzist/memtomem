"""Editable-input clipboard routing for TUI Phase 4-2."""

from __future__ import annotations

import pytest
from textual import events
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.dom import NoScreen
from textual.screen import ModalScreen

from memtomem.tui.clipboard import ClipboardAppMixin
from memtomem.tui.widgets.controls import TuiInput


class _InputHarness(ClipboardAppMixin, App[None]):
    clipboard_target_enabled = True

    def compose(self) -> ComposeResult:
        yield TuiInput(value="abcdef", id="field")

    def is_clipboard_target_active(self, widget: TuiInput) -> bool:
        if not self.clipboard_target_enabled:
            return False
        try:
            widget_screen = widget.screen
        except (NoScreen, RuntimeError):
            return False
        if (
            widget_screen is not self.screen
            or self.focused is not widget
            or widget.disabled
            or not widget.is_attached
        ):
            return False
        current = widget
        while current is not None:
            if not current.display or not current.visible:
                return False
            current = getattr(current, "parent", None)
        return True


def test_input_clipboard_bindings_are_hidden_and_keep_terminal_aliases() -> None:
    bindings = {binding.key: binding for binding in TuiInput.BINDINGS}

    assert set(bindings) == {
        "ctrl+c",
        "ctrl+x",
        "ctrl+v,ctrl+shift+v,shift+insert",
    }
    assert all(not binding.show for binding in bindings.values())


async def test_selected_text_copy_and_cut_share_the_common_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        "memtomem.tui.clipboard.write_os_clipboard",
        lambda text: copied.append(text) or True,
    )
    monkeypatch.setattr("memtomem.tui.clipboard.read_os_clipboard", lambda: None)
    app = _InputHarness()

    async with app.run_test() as pilot:
        field = app.query_one("#field", TuiInput)
        field.focus()
        await pilot.pause()

        field.selection = (1, 4)
        await pilot.press("ctrl+c")
        assert copied == ["bcd"]
        assert app.clipboard == "bcd"
        assert field.value == "abcdef"

        field.selection = (4, 1)
        await pilot.press("ctrl+x")
        assert copied == ["bcd", "bcd"]
        assert app.clipboard == "bcd"
        assert field.value == "aef"
        assert field.cursor_position == 1


async def test_shortcut_paste_keeps_only_the_first_logical_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_value = "붙여넣기\r\n둘째 줄\r\n"
    monkeypatch.setattr("memtomem.tui.clipboard.read_os_clipboard", lambda: host_value)
    app = _InputHarness()

    async with app.run_test() as pilot:
        field = app.query_one("#field", TuiInput)
        field.focus()
        field.selection = (1, 4)
        await pilot.pause()

        await pilot.press("ctrl+v")
        assert field.value == "a붙여넣기ef"
        assert "\r" not in field.value
        assert "\n" not in field.value


@pytest.mark.parametrize("payload", ["첫째\n둘째", "첫째\r\n둘째", "첫째\r둘째"])
async def test_terminal_paste_event_keeps_only_the_first_logical_line(payload: str) -> None:
    app = _InputHarness()

    async with app.run_test() as pilot:
        field = app.query_one("#field", TuiInput)
        field.focus()
        field.selection = (1, 4)
        await pilot.pause()

        field.post_message(events.Paste(payload))
        await pilot.pause()
        assert field.value == "a첫째ef"


async def test_no_selection_and_inactive_input_are_safe_no_ops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        "memtomem.tui.clipboard.write_os_clipboard",
        lambda text: copied.append(text) or True,
    )
    monkeypatch.setattr("memtomem.tui.clipboard.read_os_clipboard", lambda: "replacement")
    app = _InputHarness()

    async with app.run_test(notifications=True) as pilot:
        field = app.query_one("#field", TuiInput)
        field.focus()
        field.cursor_position = 2
        await pilot.pause()

        await pilot.press("ctrl+c")
        assert len(app._notifications) == 0

        with pytest.raises(SkipAction):
            field.action_copy()
        field.action_cut()
        assert copied == []
        assert field.value == "abcdef"

        app.clipboard_target_enabled = False
        field.selection = (1, 4)
        with pytest.raises(SkipAction):
            field.action_copy()
        field.action_cut()
        field.action_paste()
        field.post_message(events.Paste("terminal paste"))
        await pilot.pause()

        assert copied == []
        assert field.value == "abcdef"


async def test_hidden_disabled_and_modal_background_inputs_are_not_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        "memtomem.tui.clipboard.write_os_clipboard",
        lambda text: copied.append(text) or True,
    )
    monkeypatch.setattr("memtomem.tui.clipboard.read_os_clipboard", lambda: "replacement")
    app = _InputHarness()

    async with app.run_test() as pilot:
        field = app.query_one("#field", TuiInput)
        field.focus()
        field.selection = (1, 4)
        await pilot.pause()

        field.display = False
        with pytest.raises(SkipAction):
            field.action_copy()
        field.action_cut()
        field.action_paste()
        assert field.value == "abcdef"

        field.display = True
        field.disabled = True
        with pytest.raises(SkipAction):
            field.action_copy()
        field.action_cut()
        field.action_paste()
        assert field.value == "abcdef"

        field.disabled = False
        field.focus()
        app.push_screen(ModalScreen())
        await pilot.pause()
        with pytest.raises(SkipAction):
            field.action_copy()
        field.action_cut()
        field.action_paste()

        assert copied == []
        assert field.value == "abcdef"


async def test_detached_input_clipboard_actions_are_safe_no_ops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        "memtomem.tui.clipboard.write_os_clipboard",
        lambda text: copied.append(text) or True,
    )
    monkeypatch.setattr("memtomem.tui.clipboard.read_os_clipboard", lambda: "replacement")
    app = _InputHarness()

    async with app.run_test() as pilot:
        field = app.query_one("#field", TuiInput)
        field.selection = (1, 4)
        await field.remove()
        await pilot.pause()

        with pytest.raises(SkipAction):
            field.action_copy()
        field.action_cut()
        field.action_paste()

        assert copied == []
        assert field.value == "abcdef"
