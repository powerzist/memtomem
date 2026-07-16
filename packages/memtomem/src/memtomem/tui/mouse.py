"""Runtime mouse-mode control owned by Textual's active driver."""

from __future__ import annotations

from typing import Any, cast

from textual.driver import Driver


def driver_mouse_enabled(driver: Driver | None, *, default: bool = True) -> bool:
    """Return Textual's authoritative mouse flag while the app is running."""

    if driver is None:
        return default
    return bool(getattr(cast(Any, driver), "_mouse", default))


def set_driver_mouse_enabled(driver: Driver, enabled: bool) -> None:
    """Switch mouse reporting through Textual's native driver lifecycle.

    Textual 0.86 through 8.2.7 keeps the active mouse state in ``Driver._mouse``
    and terminal drivers expose matching native enable/disable helpers.  The
    helpers intentionally remain isolated here because Textual has no public
    runtime toggle API.  Disabling runs before clearing the flag so Textual can
    emit every mode reset; enabling sets it first for the inverse reason.
    """

    native_driver = cast(Any, driver)
    if not hasattr(native_driver, "_mouse"):
        raise RuntimeError("Textual driver lacks _mouse lifecycle state")
    current = bool(native_driver._mouse)
    if current == enabled:
        return

    method_name = "_enable_mouse_support" if enabled else "_disable_mouse_support"
    method = getattr(native_driver, method_name, None)
    if method is None:
        if driver.is_headless:
            native_driver._mouse = enabled
            return
        raise RuntimeError(f"Textual driver lacks {method_name}")

    if enabled:
        # Keep this true if output fails part-way through so Textual's normal
        # or exceptional shutdown path retries the complete disable sequence.
        native_driver._mouse = True
        method()
    else:
        # Native helpers guard on _mouse, so clear it only after all reset
        # sequences were written successfully.
        method()
        native_driver._mouse = False
