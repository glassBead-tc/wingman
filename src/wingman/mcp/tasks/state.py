"""Task state machine and data types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class TaskState(Enum):
    """Task lifecycle states."""

    PENDING = "pending"  # Created, not started
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Error occurred
    CANCELLED = "cancelled"  # User/timeout cancelled


class InvalidTaskTransition(Exception):
    """Invalid task state transition."""

    def __init__(self, task_id: str, from_state: TaskState, to_state: TaskState):
        self.task_id = task_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Cannot transition task {task_id} from {from_state.value} to {to_state.value}"
        )


@dataclass
class TaskProgress:
    """Progress information for a task."""

    current: int
    total: int | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP wire format."""
        result: dict[str, Any] = {"current": self.current}
        if self.total is not None:
            result["total"] = self.total
        if self.message is not None:
            result["message"] = self.message
        return result


@dataclass
class TaskError:
    """Error information for failed tasks."""

    code: int
    message: str
    data: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP wire format."""
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result


# Valid task types
TaskType = Literal["tools/call", "sampling/createMessage", "elicitation/create"]


@dataclass
class Task:
    """
    A durable task tracking an async operation.

    Tasks provide state machine abstraction for long-running operations,
    enabling async execution with progress tracking and cancellation.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: TaskType = "tools/call"
    state: TaskState = TaskState.PENDING
    progress: TaskProgress | None = None
    result: Any | None = None
    error: TaskError | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Valid state transitions
    VALID_TRANSITIONS: dict[TaskState, list[TaskState]] = field(
        default_factory=lambda: {
            TaskState.PENDING: [TaskState.RUNNING, TaskState.CANCELLED],
            TaskState.RUNNING: [
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELLED,
            ],
            TaskState.COMPLETED: [],
            TaskState.FAILED: [],
            TaskState.CANCELLED: [],
        },
        init=False,
        repr=False,
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP wire format."""
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "state": self.state.value,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }
        if self.progress:
            result["progress"] = self.progress.to_dict()
        if self.result is not None:
            result["result"] = self.result
        if self.error:
            result["error"] = self.error.to_dict()
        if self.started_at:
            result["startedAt"] = self.started_at.isoformat()
        if self.completed_at:
            result["completedAt"] = self.completed_at.isoformat()
        if self.metadata:
            result["_meta"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create task from MCP wire format."""
        task = cls(
            id=data["id"],
            type=data.get("type", "tools/call"),
            state=TaskState(data["state"]),
            metadata=data.get("_meta", {}),
        )

        # Parse datetimes
        if "createdAt" in data:
            task.created_at = datetime.fromisoformat(data["createdAt"])
        if "updatedAt" in data:
            task.updated_at = datetime.fromisoformat(data["updatedAt"])
        if "startedAt" in data:
            task.started_at = datetime.fromisoformat(data["startedAt"])
        if "completedAt" in data:
            task.completed_at = datetime.fromisoformat(data["completedAt"])

        # Parse nested objects
        if "progress" in data:
            p = data["progress"]
            task.progress = TaskProgress(
                current=p["current"],
                total=p.get("total"),
                message=p.get("message"),
            )

        if "error" in data:
            e = data["error"]
            task.error = TaskError(
                code=e["code"],
                message=e["message"],
                data=e.get("data"),
            )

        if "result" in data:
            task.result = data["result"]

        return task

    def transition(self, new_state: TaskState) -> None:
        """
        Transition to a new state with validation.

        Args:
            new_state: The target state.

        Raises:
            InvalidTaskTransition: If the transition is not allowed.
        """
        if new_state not in self.VALID_TRANSITIONS[self.state]:
            raise InvalidTaskTransition(self.id, self.state, new_state)

        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)

        if new_state == TaskState.RUNNING:
            self.started_at = datetime.now(timezone.utc)
        elif new_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            self.completed_at = datetime.now(timezone.utc)

    def update_progress(
        self, current: int, total: int | None = None, message: str | None = None
    ) -> None:
        """
        Update task progress.

        Args:
            current: Current progress value.
            total: Total value (optional).
            message: Progress message (optional).
        """
        self.progress = TaskProgress(current=current, total=total, message=message)
        self.updated_at = datetime.now(timezone.utc)

    @property
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.state in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        )

    @property
    def is_active(self) -> bool:
        """Check if task is currently active."""
        return self.state in (TaskState.PENDING, TaskState.RUNNING)

    @property
    def duration_seconds(self) -> float | None:
        """Get task execution duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def __str__(self) -> str:
        return f"Task({self.id[:8]}..., type={self.type}, state={self.state.value})"

    def __repr__(self) -> str:
        return (
            f"Task(id={self.id!r}, type={self.type!r}, "
            f"state={self.state.value!r})"
        )
