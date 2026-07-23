from __future__ import annotations

import base64
import ctypes
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest
from textual.app import App

from memtomem.tui import clipboard


class _RecordingDriver:
    def __init__(self, events: list[tuple[str, str]]) -> None:
        self.events = events

    def write(self, value: str) -> None:
        self.events.append(("osc52", value))


class _ClipboardTestApp(clipboard.ClipboardAppMixin, App[None]):
    pass


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "plain text",
        "intentional LF\n",
        "intentional CRLF\r\n",
        "한글과 漢字\tC:/memories/기록.md",
    ],
)
def test_windows_read_returns_exact_stdout_without_postprocessing(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=payload.encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(clipboard, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(clipboard, "_first_available", lambda *_commands: "powershell.exe")
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.read_os_clipboard() == payload

    command, kwargs = calls.pop()
    assert command[:3] == ["powershell.exe", "-NoProfile", "-Command"]
    script = command[3]
    assert "Get-Clipboard -Raw" in script
    assert "[Console]::Out.Write(" in script
    assert "WriteLine" not in script
    assert "encoding" not in kwargs
    assert "text" not in kwargs
    assert kwargs["timeout"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "plain text",
        "intentional LF\n",
        "intentional CRLF\r\n",
        "한글과 漢字\tC:/memories/기록.md",
    ],
)
def test_windows_write_passes_exact_text_to_powershell_stdin(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(clipboard, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(clipboard, "_first_available", lambda *_commands: "powershell.exe")
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.write_os_clipboard(payload) is True

    command, kwargs = calls.pop()
    assert command[:3] == ["powershell.exe", "-NoProfile", "-Command"]
    assert "[Console]::In.ReadToEnd()" in command[3]
    assert kwargs["input"] == payload.encode("utf-8")
    assert "encoding" not in kwargs
    assert "text" not in kwargs
    assert kwargs["timeout"] == 2


def test_missing_native_command_is_a_safe_unavailable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clipboard, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(clipboard, "_first_available", lambda *_commands: None)

    def unexpected_run(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("subprocess.run must not be called without a native command")

    monkeypatch.setattr(clipboard.subprocess, "run", unexpected_run)

    assert clipboard.read_os_clipboard() is None
    assert clipboard.write_os_clipboard("retained in app") is False


@pytest.mark.parametrize(
    "error",
    [
        OSError("native clipboard unavailable"),
        subprocess.TimeoutExpired("clipboard", 2),
    ],
)
def test_native_command_exceptions_fail_safely(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(clipboard.subprocess, "run", fail)

    assert clipboard._run_clipboard_command("clipboard-read", []) is None
    assert clipboard._send_clipboard_command("clipboard-write", [], "text") is False


def test_nonzero_native_commands_fail_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 1, stdout=b"stale", stderr=b"failure")

    monkeypatch.setattr(clipboard.subprocess, "run", fail)

    assert clipboard._run_clipboard_command("clipboard-read", []) is None
    assert clipboard._send_clipboard_command("clipboard-write", [], "text") is False


def test_invalid_native_encoding_fails_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    def invalid_utf8(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 0, stdout=b"\xff", stderr=b"")

    monkeypatch.setattr(clipboard.subprocess, "run", invalid_utf8)

    assert clipboard._run_clipboard_command("clipboard-read", []) is None
    assert clipboard._send_clipboard_command("clipboard-write", [], "\ud800") is False


@pytest.mark.parametrize(
    ("available", "expected_command", "expected_args"),
    [
        ({"pbpaste"}, "pbpaste", []),
        ({"wl-paste"}, "wl-paste", ["--no-newline"]),
        ({"xclip"}, "xclip", ["-selection", "clipboard", "-o"]),
        ({"xsel"}, "xsel", ["--clipboard", "--output"]),
    ],
)
def test_posix_read_backends_keep_existing_precedence_and_arguments(
    monkeypatch: pytest.MonkeyPatch,
    available: set[str],
    expected_command: str,
    expected_args: list[str],
) -> None:
    calls: list[tuple[str | None, list[str]]] = []
    monkeypatch.setattr(clipboard, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda command: command if command in available else None,
    )
    monkeypatch.setattr(
        clipboard,
        "_run_clipboard_command",
        lambda command, args: calls.append((command, args)) or "payload",
    )

    assert clipboard.read_os_clipboard() == "payload"
    assert calls == [(expected_command, expected_args)]


@pytest.mark.parametrize(
    ("available", "expected_command", "expected_args"),
    [
        ({"pbcopy"}, "pbcopy", []),
        ({"wl-copy"}, "wl-copy", []),
        ({"xclip"}, "xclip", ["-selection", "clipboard"]),
        ({"xsel"}, "xsel", ["--clipboard", "--input"]),
    ],
)
def test_posix_write_backends_keep_existing_precedence_and_arguments(
    monkeypatch: pytest.MonkeyPatch,
    available: set[str],
    expected_command: str,
    expected_args: list[str],
) -> None:
    calls: list[tuple[str | None, list[str], str]] = []
    monkeypatch.setattr(clipboard, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda command: command if command in available else None,
    )
    monkeypatch.setattr(
        clipboard,
        "_send_clipboard_command",
        lambda command, args, text: calls.append((command, args, text)) or True,
    )

    assert clipboard.write_os_clipboard("한글\ttext\r\n") is True
    assert calls == [(expected_command, expected_args, "한글\ttext\r\n")]


def test_app_copy_keeps_textual_mirror_and_osc52_when_native_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver(events))
    payload = "한글\tclipboard\r\n"

    def native_write(text: str) -> bool:
        events.append(("native", text))
        return False

    monkeypatch.setattr(clipboard, "write_os_clipboard", native_write)
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: None)
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: 10)

    app.copy_to_clipboard(payload)

    encoded = base64.b64encode(payload.encode("utf-8")).decode("utf-8")
    assert events == [
        ("osc52", f"\x1b]52;c;{encoded}\a"),
        ("native", payload),
    ]
    assert app.clipboard == payload


@pytest.mark.parametrize("host_text", ["", "external value", "external CRLF\r\n"])
def test_app_clipboard_prefers_any_available_host_text(
    monkeypatch: pytest.MonkeyPatch,
    host_text: str,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_clipboard", "in-process mirror")
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: host_text)

    assert app.clipboard == host_text
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: None)
    assert app.clipboard == host_text


def test_app_clipboard_falls_back_to_in_process_text_only_when_host_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_clipboard", "in-process mirror\n")
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: None)

    assert app.clipboard == "in-process mirror\n"


def test_failed_host_write_cannot_replace_new_local_copy_with_stale_host_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver([]))
    monkeypatch.setattr(clipboard, "write_os_clipboard", lambda _text: False)
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: "stale host value")
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: 10)

    app.copy_to_clipboard("new cut payload")

    assert app.clipboard == "new cut payload"


def test_external_host_change_recovers_after_a_failed_host_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver([]))
    host = ["stale host value"]
    revisions = iter((10, 10, 10, 11, 11))
    monkeypatch.setattr(clipboard, "write_os_clipboard", lambda _text: False)
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: host[0])
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: next(revisions))

    app.copy_to_clipboard("new local payload")
    assert app.clipboard == "new local payload"

    host[0] = "new external value"
    assert app.clipboard == "new external value"


def test_later_successful_host_write_restores_host_clipboard_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver([]))
    writes = iter((False, True))
    monkeypatch.setattr(clipboard, "write_os_clipboard", lambda _text: next(writes))
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: "external host value")
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: 10)

    app.copy_to_clipboard("first local payload")
    assert app.clipboard == "first local payload"

    app.copy_to_clipboard("second synchronized payload")
    assert app.clipboard == "external host value"


def test_unknown_stale_host_is_fenced_until_its_value_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver([]))
    host = ["old host value"]
    reads: list[str] = []
    monkeypatch.setattr(clipboard, "write_os_clipboard", lambda _text: False)
    monkeypatch.setattr(
        clipboard,
        "read_os_clipboard",
        lambda: reads.append(host[0]) or host[0],
    )
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: None)

    app.copy_to_clipboard("new local payload")
    assert reads == []
    assert app.clipboard == "new local payload"
    assert app.clipboard == "new local payload"

    host[0] = "new external value"
    assert app.clipboard == "new external value"


def test_revisionless_failure_does_not_trust_an_older_successful_host_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver([]))
    host = ["older observed value"]
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: None)
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: host[0])
    monkeypatch.setattr(clipboard, "write_os_clipboard", lambda _text: False)

    assert app.clipboard == "older observed value"
    host[0] = "unobserved stale value"
    app.copy_to_clipboard("new local payload")

    assert app.clipboard == "new local payload"
    assert app.clipboard == "new local payload"

    host[0] = "later external value"
    assert app.clipboard == "later external value"


def test_delayed_render_revision_change_is_observed_after_host_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver([]))
    revisions = iter((10, 10, 11))
    monkeypatch.setattr(clipboard, "write_os_clipboard", lambda _text: False)
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: "rendered host value")
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: next(revisions))

    app.copy_to_clipboard("local payload")

    assert app.clipboard == "rendered host value"


def test_zero_windows_clipboard_revision_is_treated_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Sequence:
        restype: object | None = None

        def __call__(self) -> int:
            return 0

    user32 = SimpleNamespace(GetClipboardSequenceNumber=_Sequence())
    monkeypatch.setattr(clipboard, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: user32,
        raising=False,
    )

    assert clipboard._host_clipboard_revision() is None


def test_failed_partial_host_write_fences_its_post_write_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _ClipboardTestApp()
    setattr(app, "_driver", _RecordingDriver([]))
    revisions = iter((11, 11, 11))
    monkeypatch.setattr(clipboard, "_host_clipboard_revision", lambda: next(revisions))
    monkeypatch.setattr(clipboard, "write_os_clipboard", lambda _text: False)
    monkeypatch.setattr(clipboard, "read_os_clipboard", lambda: "partial host value")

    app.copy_to_clipboard("complete local payload")

    assert app.clipboard == "complete local payload"
