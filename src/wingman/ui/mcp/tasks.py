"""Task progress UI components for MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ProgressBar, DataTable
from textual.widget import Widget
from textual.message import Message

if TYPE_CHECKING:
    from wingman.mcp.tasks.state import Task


@dataclass
class TaskCancelRequest(Message):
    """Message requesting task cancellation."""

    task_id: str


@dataclass
class TaskRefreshRequest(Message):
    """Message requesting task list refresh."""

    pass


class TaskProgressWidget(Widget):
    """Widget showing progress of a single task."""

    DEFAULT_CSS = """
    TaskProgressWidget {
        height: auto;
        padding: 1;
        border: solid $secondary;
        margin: 0 0 1 0;
    }

    TaskProgressWidget .task-header {
        text-style: bold;
    }

    TaskProgressWidget .task-type {
        color: $text-muted;
    }

    TaskProgressWidget .task-state-pending {
        color: $text-muted;
    }

    TaskProgressWidget .task-state-running {
        color: $warning;
    }

    TaskProgressWidget .task-state-completed {
        color: $success;
    }

    TaskProgressWidget .task-state-failed {
        color: $error;
    }

    TaskProgressWidget .task-state-cancelled {
        color: $text-muted;
    }

    TaskProgressWidget .task-error {
        color: $error;
        margin-top: 1;
    }

    TaskProgressWidget .task-progress-message {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(
        self,
        task: "Task",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize task progress widget.

        Args:
            task: The task to display.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.task = task

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        state_class = f"task-state-{self.task.state.value}"

        with Vertical():
            yield Static(
                f"Task: {self.task.id[:8]}...",
                classes="task-header",
            )

            yield Static(f"Type: {self.task.type}", classes="task-type")

            # State icon
            state_icons = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "cancelled": "⚪",
            }
            icon = state_icons.get(self.task.state.value, "❓")

            yield Static(
                f"{icon} State: {self.task.state.value}",
                classes=state_class,
            )

            # Progress bar if available
            if self.task.progress:
                progress = self.task.progress
                if progress.total:
                    yield ProgressBar(total=progress.total)
                    # Note: Textual ProgressBar sets progress via update
                if progress.message:
                    yield Static(progress.message, classes="task-progress-message")

            # Error message if failed
            if self.task.error:
                yield Static(
                    f"Error: {self.task.error.message}",
                    classes="task-error",
                )

            # Duration if started
            duration = self.task.duration_seconds
            if duration is not None:
                yield Static(
                    f"Duration: {duration:.1f}s",
                    classes="task-type",
                )

    def update_task(self, task: "Task") -> None:
        """
        Update the displayed task.

        Args:
            task: New task data.
        """
        self.task = task
        self.refresh()


class TaskListPanel(Widget):
    """Panel showing all active tasks."""

    BINDINGS = [
        ("c", "cancel_selected", "Cancel"),
        ("r", "refresh", "Refresh"),
        ("delete", "cancel_selected", "Cancel"),
    ]

    DEFAULT_CSS = """
    TaskListPanel {
        height: 100%;
        border: solid $primary;
    }

    TaskListPanel #task-list-header {
        dock: top;
        height: 3;
        background: $primary;
        padding: 0 1;
        text-align: center;
    }

    TaskListPanel #task-list-content {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }

    TaskListPanel #task-list-empty {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    TaskListPanel #task-list-footer {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: $surface-darken-1;
    }

    TaskListPanel .task-count {
        color: $text-muted;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize task list panel.

        Args:
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._tasks: dict[str, "Task"] = {}
        self._selected_task_id: str | None = None

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static("📋 Active Tasks", id="task-list-header")

        with Vertical(id="task-list-content"):
            yield Static("No active tasks", id="task-list-empty")

        yield Static("Press [c] to cancel, [r] to refresh", id="task-list-footer")

    def update_tasks(self, tasks: list["Task"]) -> None:
        """
        Update the task list.

        Args:
            tasks: List of tasks to display.
        """
        self._tasks = {t.id: t for t in tasks}
        self._rebuild_list()

    def add_task(self, task: "Task") -> None:
        """
        Add or update a task.

        Args:
            task: Task to add or update.
        """
        self._tasks[task.id] = task
        self._rebuild_list()

    def remove_task(self, task_id: str) -> None:
        """
        Remove a task.

        Args:
            task_id: ID of task to remove.
        """
        self._tasks.pop(task_id, None)
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Rebuild the task list display."""
        try:
            content = self.query_one("#task-list-content", Vertical)
            content.remove_children()

            if not self._tasks:
                content.mount(Static("No active tasks", id="task-list-empty"))
            else:
                for task in self._tasks.values():
                    content.mount(TaskProgressWidget(task))
        except Exception:
            pass  # Widget may not be fully mounted

    def action_cancel_selected(self) -> None:
        """Cancel the selected task."""
        if self._selected_task_id:
            self.post_message(TaskCancelRequest(task_id=self._selected_task_id))

    def action_refresh(self) -> None:
        """Refresh the task list."""
        self.post_message(TaskRefreshRequest())

    def get_stats(self) -> dict[str, int]:
        """Get task statistics."""
        stats: dict[str, int] = {}
        for task in self._tasks.values():
            state = task.state.value
            stats[state] = stats.get(state, 0) + 1
        return stats


class TaskTablePanel(Widget):
    """Panel showing tasks in a table format."""

    BINDINGS = [
        ("c", "cancel_selected", "Cancel"),
        ("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    TaskTablePanel {
        height: 100%;
        border: solid $primary;
    }

    TaskTablePanel #task-table-header {
        dock: top;
        height: 3;
        background: $primary;
        padding: 0 1;
    }

    TaskTablePanel #task-table {
        height: 1fr;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize task table panel.

        Args:
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._tasks: dict[str, "Task"] = {}

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static("📋 Tasks", id="task-table-header")

        table = DataTable(id="task-table")
        table.add_columns("ID", "Type", "State", "Progress", "Duration")
        yield table

    def update_tasks(self, tasks: list["Task"]) -> None:
        """
        Update the task table.

        Args:
            tasks: List of tasks to display.
        """
        self._tasks = {t.id: t for t in tasks}
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the task table."""
        try:
            table = self.query_one("#task-table", DataTable)
            table.clear()

            for task in self._tasks.values():
                # Progress info
                progress_str = "-"
                if task.progress:
                    if task.progress.total:
                        pct = (task.progress.current / task.progress.total) * 100
                        progress_str = f"{pct:.0f}%"
                    else:
                        progress_str = str(task.progress.current)

                # Duration
                duration_str = "-"
                if task.duration_seconds is not None:
                    duration_str = f"{task.duration_seconds:.1f}s"

                table.add_row(
                    task.id[:8] + "...",
                    task.type,
                    task.state.value,
                    progress_str,
                    duration_str,
                    key=task.id,
                )
        except Exception:
            pass

    def action_cancel_selected(self) -> None:
        """Cancel the selected task."""
        try:
            table = self.query_one("#task-table", DataTable)
            if table.cursor_row is not None:
                row = table.get_row_at(table.cursor_row)
                if row:
                    task_id = str(row.key)
                    self.post_message(TaskCancelRequest(task_id=task_id))
        except Exception:
            pass

    def action_refresh(self) -> None:
        """Refresh the task list."""
        self.post_message(TaskRefreshRequest())
