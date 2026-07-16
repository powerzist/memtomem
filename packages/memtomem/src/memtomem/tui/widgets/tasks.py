"""Task Center presentation widgets."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from memtomem.tui.application.tasks import TaskCenter, TaskRecord, TaskStatus


STATUS_SYMBOL = {
    TaskStatus.QUEUED: "[ ]",
    TaskStatus.RUNNING: "[>]",
    TaskStatus.CANCELLING: "[~]",
    TaskStatus.SUCCEEDED: "[+]",
    TaskStatus.PARTIAL: "[!]",
    TaskStatus.FAILED: "[x]",
}


class TaskRow(Static):
    def __init__(self, task: TaskRecord) -> None:
        progress = "" if task.progress is None else f" {task.progress:>3.0%}"
        text = f"{STATUS_SYMBOL[task.status]} {task.operation}\n    {task.status.value}{progress} | {task.phase}"
        super().__init__(text, classes=f"task-row task-{task.status.value}")


class TaskCenterView(VerticalScroll, can_focus=True):
    """Persistent global task surface."""

    def __init__(self, tasks: TaskCenter, *, id: str = "task-center") -> None:
        super().__init__(id=id, classes="task-center")
        self.tasks = tasks
        self._unsubscribe: Callable[[], None] | None = None

    def compose(self) -> ComposeResult:
        yield Static("[ TASK CENTER ]", classes="section-title")
        snapshot = self.tasks.snapshot()
        if not snapshot:
            yield Static("[ ] No background tasks", classes="empty-state muted")
            yield Static(
                "Tasks remain here while you navigate or resize.", classes="supporting-text muted"
            )
            return
        yield from (TaskRow(task) for task in snapshot)

    def on_mount(self) -> None:
        self._unsubscribe = self.tasks.subscribe(self._schedule_refresh)

    def on_unmount(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _schedule_refresh(self) -> None:
        if self.is_mounted:
            self.call_later(self.refresh_tasks)

    async def refresh_tasks(self) -> None:
        scroll_y = self.scroll_y
        await self.remove_children()
        await self.mount(*list(self.compose()))
        self.call_after_refresh(self.scroll_to, y=scroll_y, animate=False, force=True)
