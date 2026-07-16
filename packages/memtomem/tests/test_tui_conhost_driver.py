"""Regression tests for classic conhost viewport normalization."""

from __future__ import annotations

import os
from threading import Event
from types import SimpleNamespace

import pytest
from textual import events
from textual.geometry import Size

from memtomem.tui import app as tui_app
from memtomem.tui import conhost_driver
from memtomem.tui.conhost_driver import ConhostViewportMonitor


def _resize(width: int, height: int) -> events.Resize:
    size = Size(width, height)
    return events.Resize(size, size, container_size=size, pixel_size=Size(800, 600))


def test_driver_resize_uses_visible_viewport_instead_of_backing_buffer() -> None:
    monitor = ConhostViewportMonitor(lambda: (120, 30))

    normalized = monitor.normalize(_resize(240, 9001))

    assert isinstance(normalized, events.Resize)
    assert normalized.size == Size(120, 30)
    assert normalized.virtual_size == Size(120, 30)
    assert normalized.container_size == Size(120, 30)
    assert normalized.pixel_size == Size(800, 600)


def test_late_buffer_resize_is_normalized_again_without_racy_dedupe() -> None:
    monitor = ConhostViewportMonitor(lambda: (120, 30))

    first = monitor.normalize(_resize(240, 9001))
    late = monitor.normalize(_resize(240, 9001))

    assert isinstance(first, events.Resize)
    assert isinstance(late, events.Resize)
    assert first.size == Size(120, 30)
    assert late.size == Size(120, 30)


def test_non_resize_driver_message_is_unchanged() -> None:
    monitor = ConhostViewportMonitor(lambda: (120, 30))
    key = events.Key("x", "x")

    assert monitor.normalize(key) is key


def test_read_only_poll_emits_only_when_srwindow_changes() -> None:
    current = [(120, 30)]
    monitor = ConhostViewportMonitor(lambda: current[0])
    sent: list[events.Resize] = []

    assert monitor.poll_once(sent.append)
    assert not monitor.poll_once(sent.append)
    current[0] = (80, 24)
    assert monitor.poll_once(sent.append)

    assert [message.size for message in sent] == [Size(120, 30), Size(80, 24)]


@pytest.mark.parametrize("viewport", [None, (0, 24), (80, 0)])
def test_invalid_or_missing_viewport_falls_back_to_original_resize(
    viewport: tuple[int, int] | None,
) -> None:
    monitor = ConhostViewportMonitor(lambda: viewport)
    original = _resize(100, 40)

    assert monitor.normalize(original) is original
    assert not monitor.poll_once(lambda _: pytest.fail("invalid viewport was emitted"))


def test_viewport_reader_failure_is_non_fatal() -> None:
    def fail() -> tuple[int, int] | None:
        raise OSError("console handle unavailable")

    monitor = ConhostViewportMonitor(fail)
    original = _resize(100, 40)

    assert monitor.normalize(original) is original
    assert not monitor.poll_once(lambda _: pytest.fail("failed read was emitted"))


def test_viewport_observer_starts_once_and_stops_cleanly() -> None:
    delivered = Event()
    monitor = ConhostViewportMonitor(lambda: (120, 30), poll_seconds=0.01)

    monitor.start(lambda _: delivered.set())
    first_thread = monitor._thread
    monitor.start(lambda _: pytest.fail("a second observer was started"))

    assert delivered.wait(1)
    assert monitor._thread is first_thread
    assert monitor.is_running
    monitor.stop()
    assert not monitor.is_running


def test_driver_installation_is_limited_to_classic_windows_conhost(monkeypatch) -> None:
    original = object()
    fake_driver = object()
    app = SimpleNamespace(driver_class=original)
    monkeypatch.setattr(conhost_driver, "_get_conhost_driver_class", lambda: fake_driver)

    assert not conhost_driver.install_conhost_resize_driver(
        app,
        "windows-conhost",
        os_name="posix",  # type: ignore[arg-type]
    )
    assert app.driver_class is original
    assert not conhost_driver.install_conhost_resize_driver(
        app,
        "windows-terminal",
        os_name="nt",  # type: ignore[arg-type]
    )
    assert app.driver_class is original
    assert conhost_driver.install_conhost_resize_driver(
        app,
        "windows-conhost",
        os_name="nt",  # type: ignore[arg-type]
    )
    assert app.driver_class is fake_driver


@pytest.mark.skipif(os.name != "nt", reason="Textual's WindowsDriver imports Windows APIs")
async def test_local_windows_driver_normalizes_before_driver_delivery(monkeypatch) -> None:
    driver_class = conhost_driver._get_conhost_driver_class()
    captured: list[object] = []

    class CapturingDriver(driver_class):  # type: ignore[misc, valid-type]
        def send_message(self, message: object) -> None:
            captured.append(message)

    monkeypatch.setattr(CapturingDriver, "viewport_reader", staticmethod(lambda: (80, 24)))
    driver = CapturingDriver(SimpleNamespace(), mouse=False)
    driver._conhost_viewport_monitor = ConhostViewportMonitor(lambda: (80, 24))

    driver.process_message(_resize(200, 9001))

    assert len(captured) == 1
    delivered = captured[0]
    assert isinstance(delivered, events.Resize)
    assert delivered.size == Size(80, 24)


def test_launchers_install_the_driver_for_main_and_diagnostics(monkeypatch) -> None:
    installed: list[tuple[object, str]] = []
    ran: list[tuple[str, bool]] = []

    class FakeMainApp:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def run(self, *, mouse: bool) -> None:
            ran.append(("main", mouse))

    class FakeDiagnosticsApp:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def run(self, *, mouse: bool) -> None:
            ran.append(("diagnostics", mouse))

    monkeypatch.setattr(tui_app, "MemtomemTuiApp", FakeMainApp)
    monkeypatch.setattr(tui_app, "InputDiagnosticsApp", FakeDiagnosticsApp)
    monkeypatch.setattr(
        tui_app,
        "install_conhost_resize_driver",
        lambda app, profile: installed.append((app, profile)),
    )

    tui_app.run(terminal_profile="windows-conhost", mouse=False)
    tui_app.run_input_diagnostics(terminal_profile="windows-conhost", mouse=True)

    assert [profile for _, profile in installed] == ["windows-conhost", "windows-conhost"]
    assert ran == [("main", False), ("diagnostics", True)]
