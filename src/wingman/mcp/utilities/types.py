"""Shared types for MCP utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Literal, TypeVar


class LogLevel(Enum):
    """
    MCP log levels following RFC 5424 severity levels.

    Ordered from least to most severe.
    """

    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    ALERT = "alert"
    EMERGENCY = "emergency"

    @classmethod
    def from_string(cls, value: str) -> "LogLevel":
        """Parse log level from string value."""
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Invalid log level: {value}")

    def __lt__(self, other: "LogLevel") -> bool:
        """Compare severity (lower = less severe)."""
        order = list(LogLevel)
        return order.index(self) < order.index(other)

    def __le__(self, other: "LogLevel") -> bool:
        """Compare severity (lower = less severe)."""
        return self == other or self < other


@dataclass
class ProgressInfo:
    """
    Progress notification data from server.

    Sent via notifications/progress during long-running operations.
    """

    progress_token: str | int
    """Token identifying the operation."""

    progress: float
    """Current progress value (must increase monotonically)."""

    total: float | None = None
    """Total value if known."""

    message: str | None = None
    """Optional progress message."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgressInfo":
        """Parse from notification params."""
        return cls(
            progress_token=data["progressToken"],
            progress=float(data["progress"]),
            total=float(data["total"]) if "total" in data else None,
            message=data.get("message"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result: dict[str, Any] = {
            "progressToken": self.progress_token,
            "progress": self.progress,
        }
        if self.total is not None:
            result["total"] = self.total
        if self.message is not None:
            result["message"] = self.message
        return result

    @property
    def percentage(self) -> float | None:
        """Calculate percentage complete if total is known."""
        if self.total is not None and self.total > 0:
            return (self.progress / self.total) * 100
        return None

    @property
    def is_complete(self) -> bool:
        """Check if operation appears complete."""
        if self.total is not None:
            return self.progress >= self.total
        return False


@dataclass
class LogMessage:
    """
    Server log message notification data.

    Sent via notifications/message from server to client.
    """

    level: LogLevel
    """Severity level of the message."""

    logger: str | None = None
    """Logger name/component that generated the message."""

    data: Any = None
    """Log message data (typically string or dict)."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LogMessage":
        """Parse from notification params."""
        return cls(
            level=LogLevel.from_string(data["level"]),
            logger=data.get("logger"),
            data=data.get("data"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result: dict[str, Any] = {"level": self.level.value}
        if self.logger is not None:
            result["logger"] = self.logger
        if self.data is not None:
            result["data"] = self.data
        return result


@dataclass
class CancellationInfo:
    """
    Cancellation notification data.

    Sent via notifications/cancelled when a request is cancelled.
    """

    request_id: str
    """ID of the cancelled request."""

    reason: str | None = None
    """Optional reason for cancellation."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CancellationInfo":
        """Parse from notification params."""
        return cls(
            request_id=str(data["requestId"]),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result: dict[str, Any] = {"requestId": self.request_id}
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass
class CompletionRef:
    """
    Reference for completion context.

    Identifies the prompt or resource for which completion is requested.
    """

    type: Literal["ref/prompt", "ref/resource"]
    """Reference type."""

    name: str
    """Name of the prompt or URI of the resource."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionRef":
        """Parse from request params."""
        ref_type = data["type"]
        if ref_type not in ("ref/prompt", "ref/resource"):
            raise ValueError(f"Invalid reference type: {ref_type}")
        return cls(type=ref_type, name=data["name"])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {"type": self.type, "name": self.name}


@dataclass
class CompletionArgument:
    """Argument being completed."""

    name: str
    """Argument name."""

    value: str
    """Current partial value."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionArgument":
        """Parse from request params."""
        return cls(name=data["name"], value=data["value"])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {"name": self.name, "value": self.value}


@dataclass
class CompletionRequest:
    """
    Completion request parameters.

    Sent via completion/complete to get argument suggestions.
    """

    ref: CompletionRef
    """Reference to prompt or resource."""

    argument: CompletionArgument
    """Argument being completed."""

    context: dict[str, Any] | None = None
    """Optional context with previously resolved arguments."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionRequest":
        """Parse from request params."""
        return cls(
            ref=CompletionRef.from_dict(data["ref"]),
            argument=CompletionArgument.from_dict(data["argument"]),
            context=data.get("context"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for request params."""
        result: dict[str, Any] = {
            "ref": self.ref.to_dict(),
            "argument": self.argument.to_dict(),
        }
        if self.context is not None:
            result["context"] = self.context
        return result


@dataclass
class CompletionResponse:
    """
    Completion response data.

    Returned from completion/complete request.
    """

    values: list[str] = field(default_factory=list)
    """Completion suggestions (max 100, sorted by relevance)."""

    total: int | None = None
    """Total number of matches if known."""

    has_more: bool = False
    """Whether more results are available."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionResponse":
        """Parse from response result."""
        completion = data.get("completion", {})
        return cls(
            values=completion.get("values", []),
            total=completion.get("total"),
            has_more=completion.get("hasMore", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for response result."""
        completion: dict[str, Any] = {"values": self.values}
        if self.total is not None:
            completion["total"] = self.total
        if self.has_more:
            completion["hasMore"] = self.has_more
        return {"completion": completion}


# Generic type for paginated items
T = TypeVar("T")


@dataclass
class PaginatedResult(Generic[T]):
    """
    Result of a paginated list operation.

    Contains items and optional cursor for next page.
    """

    items: list[T] = field(default_factory=list)
    """Items in this page."""

    next_cursor: str | None = None
    """Cursor for fetching next page (None if no more pages)."""

    @property
    def has_more(self) -> bool:
        """Check if more pages are available."""
        return self.next_cursor is not None
