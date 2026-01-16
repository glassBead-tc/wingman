"""Task lifecycle management."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from wingman.mcp.tasks.state import (
    Task,
    TaskState,
    TaskError,
    InvalidTaskTransition,
)

logger = logging.getLogger(__name__)


class TooManyTasksError(Exception):
    """Too many concurrent tasks."""

    pass


@dataclass
class TaskConfig:
    """Configuration for task management."""

    default_timeout: float = 300.0  # 5 minutes
    """Default timeout for task execution."""

    completed_ttl: float = 3600.0  # 1 hour
    """Time to live for completed tasks before cleanup."""

    max_concurrent: int = 100
    """Maximum number of concurrent tasks."""

    cleanup_interval: float = 60.0  # 1 minute
    """Interval between cleanup runs."""

    persistence_enabled: bool = False
    """Whether to persist tasks to storage."""


class TaskManager:
    """
    Manages task lifecycle and execution.

    Provides:
    - Task creation and tracking
    - Background execution with timeout
    - Cancellation support
    - Progress updates
    - Automatic cleanup of completed tasks
    """

    def __init__(
        self,
        config: TaskConfig | None = None,
        on_state_change: Callable[[Task, TaskState, TaskState], Awaitable[None]]
        | None = None,
    ):
        """
        Initialize task manager.

        Args:
            config: Task configuration.
            on_state_change: Callback for state changes (task, old_state, new_state).
        """
        self.config = config or TaskConfig()
        self._on_state_change = on_state_change
        self._tasks: dict[str, Task] = {}
        self._executors: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def task_count(self) -> int:
        """Get number of tracked tasks."""
        return len(self._tasks)

    @property
    def active_task_count(self) -> int:
        """Get number of active (non-terminal) tasks."""
        return sum(1 for t in self._tasks.values() if t.is_active)

    async def start(self) -> None:
        """Start the task manager."""
        if self._started:
            return

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._started = True
        logger.info("Task manager started")

    async def stop(self) -> None:
        """Stop the task manager and cancel all tasks."""
        if not self._started:
            return

        # Stop cleanup loop
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Cancel all running tasks
        for task_id, executor in list(self._executors.items()):
            executor.cancel()
            try:
                await executor
            except asyncio.CancelledError:
                pass

            task = self._tasks.get(task_id)
            if task and task.state == TaskState.RUNNING:
                try:
                    await self._transition_task(task, TaskState.CANCELLED)
                except InvalidTaskTransition:
                    pass

        self._started = False
        logger.info("Task manager stopped")

    async def create_task(
        self,
        task_type: str,
        executor: Callable[[Task], Awaitable[Any]],
        metadata: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Task:
        """
        Create and start a new task.

        Args:
            task_type: Type of task (e.g., "tools/call", "sampling/createMessage").
            executor: Async function to execute.
            metadata: Optional metadata dict.
            timeout: Optional custom timeout (uses default if not specified).

        Returns:
            The created Task.

        Raises:
            TooManyTasksError: If max concurrent tasks reached.
        """
        async with self._lock:
            active_count = sum(1 for t in self._tasks.values() if t.is_active)
            if active_count >= self.config.max_concurrent:
                raise TooManyTasksError(
                    f"Maximum {self.config.max_concurrent} concurrent tasks"
                )

            task = Task(
                type=task_type,  # type: ignore
                metadata=metadata or {},
            )
            self._tasks[task.id] = task

        logger.debug(f"Created task {task.id} of type {task_type}")

        # Start execution in background
        task_timeout = timeout or self.config.default_timeout
        self._executors[task.id] = asyncio.create_task(
            self._execute_task(task, executor, task_timeout)
        )

        return task

    async def _execute_task(
        self,
        task: Task,
        executor: Callable[[Task], Awaitable[Any]],
        timeout: float,
    ) -> None:
        """Execute a task with timeout and error handling."""
        try:
            await self._transition_task(task, TaskState.RUNNING)

            # Execute with timeout
            result = await asyncio.wait_for(
                executor(task),
                timeout=timeout,
            )

            task.result = result
            await self._transition_task(task, TaskState.COMPLETED)
            logger.debug(f"Task {task.id} completed successfully")

        except asyncio.TimeoutError:
            task.error = TaskError(
                code=-32001,
                message=f"Task timed out after {timeout}s",
            )
            await self._transition_task(task, TaskState.FAILED)
            logger.warning(f"Task {task.id} timed out")

        except asyncio.CancelledError:
            try:
                await self._transition_task(task, TaskState.CANCELLED)
            except InvalidTaskTransition:
                pass
            logger.debug(f"Task {task.id} cancelled")
            raise

        except Exception as e:
            task.error = TaskError(
                code=-32603,
                message=str(e),
            )
            await self._transition_task(task, TaskState.FAILED)
            logger.error(f"Task {task.id} failed: {e}")

        finally:
            self._executors.pop(task.id, None)

    async def _transition_task(self, task: Task, new_state: TaskState) -> None:
        """Transition task state with callback."""
        old_state = task.state
        task.transition(new_state)

        if self._on_state_change:
            try:
                await self._on_state_change(task, old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    async def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        state: TaskState | None = None,
        task_type: str | None = None,
    ) -> list[Task]:
        """
        List tasks with optional filtering.

        Args:
            state: Filter by state.
            task_type: Filter by type.

        Returns:
            List of matching tasks.
        """
        tasks = list(self._tasks.values())

        if state is not None:
            tasks = [t for t in tasks if t.state == state]
        if task_type is not None:
            tasks = [t for t in tasks if t.type == task_type]

        return tasks

    async def cancel_task(self, task_id: str, reason: str | None = None) -> bool:
        """
        Cancel a task.

        Args:
            task_id: ID of task to cancel.
            reason: Optional cancellation reason.

        Returns:
            True if successfully cancelled, False otherwise.
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.is_terminal:
            return False  # Already terminal

        # Cancel the executor
        executor = self._executors.get(task_id)
        if executor:
            executor.cancel()
            try:
                await executor
            except asyncio.CancelledError:
                pass

        # Update task state if not already cancelled
        if task.state != TaskState.CANCELLED:
            try:
                await self._transition_task(task, TaskState.CANCELLED)
                if reason:
                    task.metadata["cancel_reason"] = reason
                logger.info(f"Task {task_id} cancelled: {reason or 'no reason'}")
                return True
            except InvalidTaskTransition:
                return False

        return True

    async def update_progress(
        self,
        task_id: str,
        current: int,
        total: int | None = None,
        message: str | None = None,
    ) -> bool:
        """
        Update task progress.

        Args:
            task_id: ID of task to update.
            current: Current progress value.
            total: Total value (optional).
            message: Progress message (optional).

        Returns:
            True if updated, False if task not found or not running.
        """
        task = self._tasks.get(task_id)
        if task and task.state == TaskState.RUNNING:
            task.update_progress(current, total, message)
            logger.debug(f"Task {task_id} progress: {current}/{total or '?'}")
            return True
        return False

    async def _cleanup_loop(self) -> None:
        """Periodically clean up completed tasks."""
        while True:
            await asyncio.sleep(self.config.cleanup_interval)
            await self._cleanup_completed()

    async def _cleanup_completed(self) -> None:
        """Remove old completed tasks."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            ttl = timedelta(seconds=self.config.completed_ttl)

            to_remove = []
            for task_id, task in self._tasks.items():
                if task.is_terminal and task.completed_at:
                    if (now - task.completed_at) > ttl:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]

            if to_remove:
                logger.debug(f"Cleaned up {len(to_remove)} completed tasks")

    def get_stats(self) -> dict[str, Any]:
        """Get task manager statistics."""
        state_counts: dict[str, int] = {}
        for task in self._tasks.values():
            state_counts[task.state.value] = state_counts.get(task.state.value, 0) + 1

        return {
            "total_tasks": len(self._tasks),
            "active_executors": len(self._executors),
            "by_state": state_counts,
            "max_concurrent": self.config.max_concurrent,
        }
