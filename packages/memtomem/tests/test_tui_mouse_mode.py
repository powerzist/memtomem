"""Regression tests for Textual-owned mouse mode lifecycle."""

from __future__ import annotations

from typing import cast

import pytest
from textual.app import App
from textual.driver import Driver

from memtomem.tui.mouse import driver_mouse_enabled, set_driver_mouse_enabled

ENABLE_MOUSE = (
    "\x1b[?1000h",
    "\x1b[?1003h",
    "\x1b[?1015h",
    "\x1b[?1006h",
)
DISABLE_MOUSE = tuple(sequence.replace("h", "l") for sequence in ENABLE_MOUSE)


class _CapturingTerminalDriver:
    """Small stand-in with Textual 0.86/8.2.7's native mouse contract."""

    is_headless = False

    def __init__(self, *, mouse: bool) -> None:
        self._mouse = mouse
        self.output: list[str] = []
        self.flush_count = 0
        self.fail_enable_once = False
        self.fail_disable_once = False

    def _enable_mouse_support(self) -> None:
        if self._mouse:
            if self.fail_enable_once:
                self.fail_enable_once = False
                self.output.append(ENABLE_MOUSE[0])
                raise OSError("simulated terminal write failure")
            self.output.extend(ENABLE_MOUSE)
            self.flush_count += 1

    def _disable_mouse_support(self) -> None:
        if not self._mouse:
            return
        if self.fail_disable_once:
            self.fail_disable_once = False
            self.output.append(DISABLE_MOUSE[0])
            raise OSError("simulated terminal write failure")
        self.output.extend(DISABLE_MOUSE)
        self.flush_count += 1


def test_runtime_toggle_uses_every_textual_mouse_mode() -> None:
    driver = _CapturingTerminalDriver(mouse=False)

    set_driver_mouse_enabled(cast(Driver, driver), True)
    set_driver_mouse_enabled(cast(Driver, driver), True)
    assert driver_mouse_enabled(cast(Driver, driver)) is True
    assert driver.output == list(ENABLE_MOUSE)

    set_driver_mouse_enabled(cast(Driver, driver), False)
    set_driver_mouse_enabled(cast(Driver, driver), False)
    assert driver_mouse_enabled(cast(Driver, driver)) is False
    assert driver.output == [*ENABLE_MOUSE, *DISABLE_MOUSE]
    assert driver.flush_count == 2


def test_failed_enable_keeps_driver_armed_for_exception_cleanup() -> None:
    driver = _CapturingTerminalDriver(mouse=False)
    driver.fail_enable_once = True

    with pytest.raises(OSError, match="simulated terminal write failure"):
        set_driver_mouse_enabled(cast(Driver, driver), True)

    assert driver_mouse_enabled(cast(Driver, driver)) is True
    set_driver_mouse_enabled(cast(Driver, driver), False)
    assert driver_mouse_enabled(cast(Driver, driver)) is False
    assert driver.output[-4:] == list(DISABLE_MOUSE)


def test_failed_disable_keeps_driver_armed_for_exception_cleanup() -> None:
    driver = _CapturingTerminalDriver(mouse=True)
    driver.fail_disable_once = True

    with pytest.raises(OSError, match="simulated terminal write failure"):
        set_driver_mouse_enabled(cast(Driver, driver), False)

    assert driver_mouse_enabled(cast(Driver, driver)) is True
    driver._disable_mouse_support()
    assert driver.output[-4:] == list(DISABLE_MOUSE)


class _LifecycleDriver(Driver):
    instances: list[_LifecycleDriver] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.output: list[str] = []
        self.__class__.instances.append(self)

    def write(self, data: str) -> None:
        self.output.append(data)

    def _enable_mouse_support(self) -> None:
        if self._mouse:
            self.output.extend(ENABLE_MOUSE)

    def _disable_mouse_support(self) -> None:
        if self._mouse:
            self.output.extend(DISABLE_MOUSE)

    def start_application_mode(self) -> None:
        self._enable_mouse_support()

    def disable_input(self) -> None:
        self._disable_mouse_support()

    def stop_application_mode(self) -> None:
        self.disable_input()


class _LifecycleApp(App[None]):
    def __init__(self, *, fail: bool) -> None:
        super().__init__(driver_class=_LifecycleDriver)
        self.fail = fail

    def on_mount(self) -> None:
        assert self._driver is not None
        set_driver_mouse_enabled(self._driver, True)
        if self.fail:
            raise RuntimeError("simulated app failure")
        self.exit()


@pytest.mark.parametrize("fail", [False, True])
def test_no_mouse_runtime_enable_is_restored_on_normal_and_exception_exit(
    fail: bool,
) -> None:
    _LifecycleDriver.instances.clear()

    _LifecycleApp(fail=fail).run(mouse=False)

    driver = _LifecycleDriver.instances[-1]
    assert driver.output[:4] == list(ENABLE_MOUSE)
    assert any(
        driver.output[index : index + 4] == list(DISABLE_MOUSE)
        for index in range(len(driver.output) - 3)
    )
