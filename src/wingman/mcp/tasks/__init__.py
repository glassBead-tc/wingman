"""
MCP Tasks Feature.

Implements durable, long-running operations with state tracking.
"""

from wingman.mcp.tasks.state import (
    Task,
    TaskState,
    TaskProgress,
    TaskError,
    InvalidTaskTransition,
)
from wingman.mcp.tasks.manager import (
    TaskManager,
    TaskConfig,
    TooManyTasksError,
)
from wingman.mcp.tasks.handlers import (
    TasksHandler,
    TaskNotFoundError,
    TaskNotCancellableError,
)
from wingman.mcp.tasks.augmented import (
    TaskAugmentedSampling,
    TaskAugmentedElicitation,
)
from wingman.mcp.tasks.persistence import TaskPersistence

__all__ = [
    # State
    "Task",
    "TaskState",
    "TaskProgress",
    "TaskError",
    "InvalidTaskTransition",
    # Manager
    "TaskManager",
    "TaskConfig",
    "TooManyTasksError",
    # Handlers
    "TasksHandler",
    "TaskNotFoundError",
    "TaskNotCancellableError",
    # Augmented operations
    "TaskAugmentedSampling",
    "TaskAugmentedElicitation",
    # Persistence
    "TaskPersistence",
]
