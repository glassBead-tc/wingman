"""Task request handlers for MCP."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from wingman.mcp.tasks.state import Task, TaskState

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient
    from wingman.mcp.tasks.manager import TaskManager

logger = logging.getLogger(__name__)


class TaskNotFoundError(Exception):
    """Task not found."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class TaskNotCancellableError(Exception):
    """Task cannot be cancelled."""

    def __init__(self, task_id: str, state: TaskState):
        self.task_id = task_id
        self.state = state
        super().__init__(
            f"Task {task_id} cannot be cancelled (state: {state.value})"
        )


class TasksHandler:
    """
    Handles tasks-related MCP requests.

    Implements:
    - tasks/list: Enumerate tasks
    - tasks/get: Get task details
    - tasks/cancel: Cancel a task
    """

    def __init__(self, manager: "TaskManager"):
        """
        Initialize handler.

        Args:
            manager: TaskManager to use.
        """
        self.manager = manager

    async def handle_list(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """
        Handle tasks/list request.

        Args:
            params: Optional filter parameters.
                - state: Filter by task state
                - type: Filter by task type

        Returns:
            Response with 'tasks' list.
        """
        params = params or {}

        # Parse filter parameters
        state = None
        if "state" in params:
            try:
                state = TaskState(params["state"])
            except ValueError:
                logger.warning(f"Invalid task state filter: {params['state']}")

        task_type = params.get("type")

        tasks = await self.manager.list_tasks(state=state, task_type=task_type)

        logger.debug(f"Listed {len(tasks)} tasks")
        return {
            "tasks": [task.to_dict() for task in tasks],
        }

    async def handle_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Handle tasks/get request.

        Args:
            params: Request parameters.
                - taskId: ID of task to get (required)

        Returns:
            Response with 'task' object.

        Raises:
            TaskNotFoundError: If task doesn't exist.
        """
        task_id = params.get("taskId")
        if not task_id:
            raise ValueError("taskId is required")

        task = await self.manager.get_task(task_id)

        if not task:
            raise TaskNotFoundError(task_id)

        logger.debug(f"Retrieved task {task_id}")
        return {"task": task.to_dict()}

    async def handle_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Handle tasks/cancel request.

        Args:
            params: Request parameters.
                - taskId: ID of task to cancel (required)
                - reason: Optional cancellation reason

        Returns:
            Response with 'cancelled' boolean.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            TaskNotCancellableError: If task cannot be cancelled.
        """
        task_id = params.get("taskId")
        if not task_id:
            raise ValueError("taskId is required")

        reason = params.get("reason")

        success = await self.manager.cancel_task(task_id, reason)

        if not success:
            task = await self.manager.get_task(task_id)
            if not task:
                raise TaskNotFoundError(task_id)
            raise TaskNotCancellableError(task_id, task.state)

        logger.info(f"Cancelled task {task_id}: {reason or 'no reason'}")
        return {"cancelled": True}

    def register_handlers(self, client: "MCPClient") -> None:
        """
        Register task handlers with MCP client.

        Args:
            client: MCPClient to register handlers on.
        """
        client.on_request("tasks/list", self.handle_list)
        client.on_request("tasks/get", self.handle_get)
        client.on_request("tasks/cancel", self.handle_cancel)
        logger.debug("Registered tasks handlers")


async def poll_task_until_complete(
    client: "MCPClient",
    task_id: str,
    poll_interval: float = 1.0,
    timeout: float = 300.0,
) -> Task:
    """
    Poll a task until it reaches a terminal state.

    Useful for servers that don't support SSE streaming.

    Args:
        client: MCPClient to use for polling.
        task_id: ID of task to poll.
        poll_interval: Seconds between polls.
        timeout: Maximum time to wait.

    Returns:
        The completed Task.

    Raises:
        TimeoutError: If task doesn't complete within timeout.
        TaskNotFoundError: If task is not found.
    """
    import asyncio
    from datetime import datetime, timezone

    start = datetime.now(timezone.utc)
    while True:
        response = await client.request("tasks/get", {"taskId": task_id})
        task_data = response.get("task")

        if not task_data:
            raise TaskNotFoundError(task_id)

        task = Task.from_dict(task_data)

        if task.is_terminal:
            return task

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        if elapsed > timeout:
            raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")

        await asyncio.sleep(poll_interval)
