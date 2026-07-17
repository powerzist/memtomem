"""Application-level ownership of Phase 3 operation and runtime services."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Static

from memtomem.config import Mem2MemConfig
from memtomem.tui.application.contracts import (
    OperationExitPolicy,
    OperationResult,
    OperationSpec,
)
from memtomem.tui.application.operations import OperationRunner
from memtomem.tui.application.runtime import RuntimeManager
from memtomem.tui.runtime import TuiPaths
from memtomem.tui.screens.shell import MemtomemTuiApp


def _paths(tmp_path: Path) -> TuiPaths:
    root = tmp_path / ".dev" / ".memtomem"
    return TuiPaths(
        mode="dev",
        project_root=tmp_path,
        state_root=root,
        config_path=root / "config.json",
        config_d_path=root / "config.d",
        database_path=root / "memtomem.db",
        memories_path=root / "memories",
    )


async def test_external_app_stop_closes_unstarted_services_without_bootstrap(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    runner = OperationRunner()
    runtime = RuntimeManager[object](paths)
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-terminal",
        paths=paths,
        operation_runner=runner,
        runtime_manager=runtime,
    )

    async with app.run_test(size=(60, 16)):
        assert not runtime.started
        assert not runner.is_closed

    assert runtime.generation == 0
    assert runtime.closed
    assert runtime.close_complete
    assert runner.is_closed


async def test_block_on_exit_operation_keeps_app_open_and_reports_safe_error(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    runner = OperationRunner()
    runtime = RuntimeManager[object](paths)
    release = asyncio.Event()

    async def critical_operation(
        _request: None,
        _context: object,
    ) -> OperationResult[None]:
        await release.wait()
        return OperationResult.succeeded()

    handle = runner.start(
        OperationSpec(
            name="Critical migration",
            exit_policy=OperationExitPolicy.BLOCK,
        ),
        None,
        critical_operation,
    )
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-terminal",
        paths=paths,
        operation_runner=runner,
        runtime_manager=runtime,
    )

    async with app.run_test(size=(60, 16)) as pilot:
        await pilot.pause()
        assert await app._shutdown_services() is False
        assert not runtime.closed
        banner = app.query_one("#global-error", Static)
        assert banner.display
        assert "TUI-EXIT-BLOCKED" in str(banner.render())
        assert "Critical migration" not in str(banner.render())

        release.set()
        await handle.result()
        assert await app._shutdown_services()
        assert runner.is_closed
        assert runtime.close_complete


async def test_external_unmount_force_closes_blocking_operation_and_runtime(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    runner = OperationRunner()
    runtime = RuntimeManager[object](paths)
    started = asyncio.Event()

    async def critical_operation(
        _request: None,
        _context: object,
    ) -> OperationResult[None]:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    handle = runner.start(
        OperationSpec(
            name="Critical migration",
            exit_policy=OperationExitPolicy.BLOCK,
        ),
        None,
        critical_operation,
    )
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-terminal",
        paths=paths,
        operation_runner=runner,
        runtime_manager=runtime,
    )

    async with app.run_test(size=(60, 16)):
        await started.wait()
        assert handle.snapshot.is_active

    assert runner.is_closed
    assert handle.snapshot.status.value == "cancelled"
    assert runtime.closed
    assert runtime.close_complete


async def test_runtime_close_failure_is_reported_before_a_second_exit_confirmation(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)

    async def factory(
        _config: Mem2MemConfig,
        *,
        load_persisted_config: bool,
    ) -> object:
        assert load_persisted_config is False
        return object()

    async def failing_closer(_components: object) -> None:
        raise RuntimeError("private close detail")

    runtime = RuntimeManager[object](
        paths,
        config_loader=lambda _paths: Mem2MemConfig(),
        factory=factory,
        closer=failing_closer,
        environment={},
    )
    await runtime.bootstrap()
    runner = OperationRunner()
    app = MemtomemTuiApp(
        startup_refresh=False,
        terminal_profile="windows-terminal",
        paths=paths,
        operation_runner=runner,
        runtime_manager=runtime,
    )

    async with app.run_test(size=(60, 16)):
        assert await app._shutdown_services() is False
        assert app.state.error is not None
        assert app.state.error.code == "TUI-RUNTIME-CLOSE"
        assert "private close detail" not in str(app.state.error)
        assert runtime.close_complete
        assert await app._shutdown_services() is True
