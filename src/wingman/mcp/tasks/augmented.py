"""Task-augmented operations for MCP.

Wraps sampling and elicitation requests in tasks for durability.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from wingman.mcp.tasks.state import Task

if TYPE_CHECKING:
    from wingman.mcp.tasks.manager import TaskManager
    from wingman.mcp.features.sampling import SamplingHandler
    from wingman.mcp.features.elicitation import ElicitationHandler

logger = logging.getLogger(__name__)


class TaskAugmentedSampling:
    """
    Wraps sampling in task for durability.

    When a server requests sampling/createMessage with task support,
    this wraps the operation in a task for tracking and cancellation.
    """

    def __init__(
        self,
        task_manager: "TaskManager",
        sampling_handler: "SamplingHandler",
    ):
        """
        Initialize task-augmented sampling.

        Args:
            task_manager: TaskManager for task lifecycle.
            sampling_handler: SamplingHandler for actual execution.
        """
        self.task_manager = task_manager
        self.sampling_handler = sampling_handler

    async def create_message_as_task(
        self,
        params: dict[str, Any],
        timeout: float | None = None,
    ) -> Task:
        """
        Execute sampling as a task.

        Args:
            params: Sampling request parameters.
            timeout: Optional custom timeout.

        Returns:
            Task wrapping the sampling operation.
        """

        async def executor(task: Task) -> dict[str, Any]:
            logger.debug(f"Executing sampling task {task.id}")
            return await self.sampling_handler.handle_request(params)

        task = await self.task_manager.create_task(
            task_type="sampling/createMessage",
            executor=executor,
            metadata={
                "method": "sampling/createMessage",
                "message_count": len(params.get("messages", [])),
            },
            timeout=timeout,
        )

        logger.info(f"Created sampling task {task.id}")
        return task


class TaskAugmentedElicitation:
    """
    Wraps elicitation in task for durability.

    When a server requests elicitation/create with task support,
    this wraps the operation in a task for tracking and cancellation.
    """

    def __init__(
        self,
        task_manager: "TaskManager",
        elicitation_handler: "ElicitationHandler",
    ):
        """
        Initialize task-augmented elicitation.

        Args:
            task_manager: TaskManager for task lifecycle.
            elicitation_handler: ElicitationHandler for actual execution.
        """
        self.task_manager = task_manager
        self.elicitation_handler = elicitation_handler

    async def create_as_task(
        self,
        params: dict[str, Any],
        timeout: float | None = None,
    ) -> Task:
        """
        Execute elicitation as a task.

        Args:
            params: Elicitation request parameters.
            timeout: Optional custom timeout.

        Returns:
            Task wrapping the elicitation operation.
        """

        async def executor(task: Task) -> dict[str, Any]:
            logger.debug(f"Executing elicitation task {task.id}")
            return await self.elicitation_handler.handle_request(params)

        # Determine elicitation type for metadata
        elicitation_type = "form"
        if params.get("url"):
            elicitation_type = "url"
        elif not params.get("requestedSchema"):
            elicitation_type = "simple"

        task = await self.task_manager.create_task(
            task_type="elicitation/create",
            executor=executor,
            metadata={
                "method": "elicitation/create",
                "elicitation_type": elicitation_type,
            },
            timeout=timeout,
        )

        logger.info(f"Created elicitation task {task.id} (type={elicitation_type})")
        return task


class TaskAugmentedToolCall:
    """
    Wraps tool calls in task for durability.

    When a client performs tools/call with task support,
    this wraps the operation in a task for tracking.
    """

    def __init__(self, task_manager: "TaskManager"):
        """
        Initialize task-augmented tool calls.

        Args:
            task_manager: TaskManager for task lifecycle.
        """
        self.task_manager = task_manager
        self._tool_executors: dict[str, Any] = {}

    def register_tool(
        self,
        tool_name: str,
        executor: Any,
    ) -> None:
        """
        Register a tool executor.

        Args:
            tool_name: Name of the tool.
            executor: Async callable to execute the tool.
        """
        self._tool_executors[tool_name] = executor

    async def call_as_task(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Task:
        """
        Execute tool call as a task.

        Args:
            tool_name: Name of tool to call.
            arguments: Tool arguments.
            timeout: Optional custom timeout.

        Returns:
            Task wrapping the tool call.

        Raises:
            ValueError: If tool not registered.
        """
        if tool_name not in self._tool_executors:
            raise ValueError(f"Unknown tool: {tool_name}")

        executor_func = self._tool_executors[tool_name]

        async def executor(task: Task) -> Any:
            logger.debug(f"Executing tool task {task.id}: {tool_name}")
            return await executor_func(arguments or {})

        task = await self.task_manager.create_task(
            task_type="tools/call",
            executor=executor,
            metadata={
                "method": "tools/call",
                "tool_name": tool_name,
            },
            timeout=timeout,
        )

        logger.info(f"Created tool task {task.id}: {tool_name}")
        return task
