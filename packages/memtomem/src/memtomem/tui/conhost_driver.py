"""Read-only conhost viewport normalization for Textual's Windows driver."""

from __future__ import annotations

import os
from collections.abc import Callable
from threading import Event, Lock, Thread, current_thread
from typing import Any

from textual import events
from textual.app import App
from textual.driver import Driver
from textual.geometry import Size
from textual.message import Message

from memtomem.tui.terminal import windows_console_viewport_size

Viewport = tuple[int, int]
ViewportReader = Callable[[], Viewport | None]
ResizeSink = Callable[[events.Resize], None]


def _resize_for_viewport(message: events.Resize, viewport: Viewport) -> events.Resize:
    """Copy a resize event while replacing buffer dimensions with visible dimensions."""

    size = Size(*viewport)
    return events.Resize(
        size,
        size,
        container_size=size,
        pixel_size=message.pixel_size,
    )


class ConhostViewportMonitor:
    """Normalize resize messages and observe window-only viewport changes.

    Classic conhost keeps a backing screen buffer separate from its visible
    ``srWindow`` rectangle. Textual's Windows input driver reports the former,
    so every incoming resize is normalized before delivery. A small read-only
    monitor covers restores that change only ``srWindow`` and therefore emit no
    ``WINDOW_BUFFER_SIZE_EVENT``.
    """

    def __init__(self, reader: ViewportReader, *, poll_seconds: float = 0.1) -> None:
        self._reader = reader
        self._poll_seconds = poll_seconds
        self._last_viewport: Viewport | None = None
        self._last_viewport_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        """Return whether the read-only viewport observer is alive."""

        return self._thread is not None and self._thread.is_alive()

    def normalize(self, message: Message) -> Message:
        """Replace a driver resize with the current visible viewport size."""

        if not isinstance(message, events.Resize):
            return message
        viewport = self._read_viewport()
        if viewport is None:
            return message
        self._remember(viewport)
        return _resize_for_viewport(message, viewport)

    def poll_once(self, sink: ResizeSink) -> bool:
        """Send one resize when the visible viewport changed without an input event."""

        viewport = self._read_viewport()
        if viewport is None or self._stop_event.is_set() or not self._remember(viewport):
            return False
        size = Size(*viewport)
        sink(events.Resize(size, size, container_size=size))
        return True

    def start(self, sink: ResizeSink) -> None:
        """Start observing ``srWindow`` without mutating the console buffer."""

        if self.is_running:
            return
        with self._last_viewport_lock:
            self._last_viewport = None
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            args=(sink,),
            daemon=True,
            name="memtomem-conhost-viewport",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the observer without blocking application shutdown indefinitely."""

        thread = self._thread
        if thread is None:
            return
        self._stop_event.set()
        if thread is not current_thread():
            thread.join(timeout=max(1.0, self._poll_seconds * 5))
        self._thread = None

    def _run(self, sink: ResizeSink) -> None:
        while not self._stop_event.wait(self._poll_seconds):
            try:
                self.poll_once(sink)
            except RuntimeError:
                # The Textual loop may close between the stop check and the
                # thread-safe delivery call. Shutdown must stay quiet.
                if self._stop_event.is_set():
                    return

    def _read_viewport(self) -> Viewport | None:
        try:
            viewport = self._reader()
        except (AttributeError, OSError, RuntimeError, ValueError):
            return None
        if viewport is None or viewport[0] <= 0 or viewport[1] <= 0:
            return None
        return viewport

    def _remember(self, viewport: Viewport) -> bool:
        with self._last_viewport_lock:
            changed = viewport != self._last_viewport
            self._last_viewport = viewport
        return changed


_CONHOST_DRIVER_CLASS: type[Driver] | None = None


def _get_conhost_driver_class() -> type[Driver]:
    """Build the Windows-only driver lazily so non-Windows imports stay safe."""

    global _CONHOST_DRIVER_CLASS
    if _CONHOST_DRIVER_CLASS is not None:
        return _CONHOST_DRIVER_CLASS

    from textual.drivers.windows_driver import WindowsDriver

    class ConhostWindowsDriver(WindowsDriver):
        """Textual Windows driver using conhost's visible window as its size."""

        viewport_reader: ViewportReader = staticmethod(windows_console_viewport_size)
        viewport_poll_seconds = 0.1

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._conhost_viewport_monitor = ConhostViewportMonitor(
                self.viewport_reader,
                poll_seconds=self.viewport_poll_seconds,
            )

        def process_message(self, message: Message) -> None:
            super().process_message(self._conhost_viewport_monitor.normalize(message))

        def start_application_mode(self) -> None:
            super().start_application_mode()
            self._conhost_viewport_monitor.start(self._send_polled_viewport)

        def stop_application_mode(self) -> None:
            self._conhost_viewport_monitor.stop()
            super().stop_application_mode()

        def disable_input(self) -> None:
            self._conhost_viewport_monitor.stop()
            super().disable_input()

        def close(self) -> None:
            self._conhost_viewport_monitor.stop()
            super().close()

        def _send_polled_viewport(self, message: events.Resize) -> None:
            # Bypass this class's normalization: the monitor already read the
            # authoritative viewport and the base method is thread-safe.
            super(ConhostWindowsDriver, self).process_message(message)

    _CONHOST_DRIVER_CLASS = ConhostWindowsDriver
    return ConhostWindowsDriver


def install_conhost_resize_driver(
    app: App[Any],
    terminal_profile: str,
    *,
    os_name: str | None = None,
) -> bool:
    """Install the local driver only for classic Windows conhost sessions."""

    os_name = os.name if os_name is None else os_name
    if os_name != "nt" or terminal_profile != "windows-conhost":
        return False
    app.driver_class = _get_conhost_driver_class()
    return True
