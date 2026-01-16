"""Protocol error types and error codes."""

from dataclasses import dataclass
from typing import Any

# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Custom MCP error codes (-32000 to -32099 reserved for implementation)
REQUEST_TIMEOUT = -32001
REQUEST_CANCELLED = -32002
SESSION_EXPIRED = -32003
CAPABILITY_NOT_SUPPORTED = -32004
VALIDATION_FAILED = -32005

# Error code to message mapping
ERROR_MESSAGES = {
    PARSE_ERROR: "Parse error",
    INVALID_REQUEST: "Invalid Request",
    METHOD_NOT_FOUND: "Method not found",
    INVALID_PARAMS: "Invalid params",
    INTERNAL_ERROR: "Internal error",
    REQUEST_TIMEOUT: "Request timeout",
    REQUEST_CANCELLED: "Request cancelled",
    SESSION_EXPIRED: "Session expired",
    CAPABILITY_NOT_SUPPORTED: "Capability not supported",
    VALIDATION_FAILED: "Validation failed",
}


@dataclass
class MCPError(Exception):
    """
    MCP protocol error.

    Represents errors from the JSON-RPC layer or MCP protocol.
    Can be converted to/from JSON-RPC error objects.
    """

    code: int
    message: str
    data: dict[str, Any] | None = None

    def __post_init__(self):
        # Set exception message
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-RPC error object."""
        error = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            error["data"] = self.data
        return error

    @classmethod
    def from_dict(cls, error: dict[str, Any]) -> "MCPError":
        """Create from JSON-RPC error object."""
        return cls(
            code=error.get("code", INTERNAL_ERROR),
            message=error.get("message", "Unknown error"),
            data=error.get("data"),
        )

    @classmethod
    def from_response(cls, error: dict[str, Any]) -> "MCPError":
        """Alias for from_dict for compatibility."""
        return cls.from_dict(error)

    @classmethod
    def parse_error(cls, details: str | None = None) -> "MCPError":
        """Create a parse error."""
        return cls(
            code=PARSE_ERROR,
            message=ERROR_MESSAGES[PARSE_ERROR],
            data={"details": details} if details else None,
        )

    @classmethod
    def invalid_request(cls, details: str | None = None) -> "MCPError":
        """Create an invalid request error."""
        return cls(
            code=INVALID_REQUEST,
            message=ERROR_MESSAGES[INVALID_REQUEST],
            data={"details": details} if details else None,
        )

    @classmethod
    def method_not_found(cls, method: str) -> "MCPError":
        """Create a method not found error."""
        return cls(
            code=METHOD_NOT_FOUND,
            message=f"Method not found: {method}",
            data={"method": method},
        )

    @classmethod
    def invalid_params(cls, details: str | None = None) -> "MCPError":
        """Create an invalid params error."""
        return cls(
            code=INVALID_PARAMS,
            message=ERROR_MESSAGES[INVALID_PARAMS],
            data={"details": details} if details else None,
        )

    @classmethod
    def internal_error(cls, details: str | None = None) -> "MCPError":
        """Create an internal error."""
        return cls(
            code=INTERNAL_ERROR,
            message=details or ERROR_MESSAGES[INTERNAL_ERROR],
        )

    @classmethod
    def timeout(cls, timeout_seconds: float) -> "MCPError":
        """Create a request timeout error."""
        return cls(
            code=REQUEST_TIMEOUT,
            message=f"Request timed out after {timeout_seconds}s",
            data={"timeout": timeout_seconds},
        )

    @classmethod
    def cancelled(cls, reason: str | None = None) -> "MCPError":
        """Create a request cancelled error."""
        return cls(
            code=REQUEST_CANCELLED,
            message=reason or ERROR_MESSAGES[REQUEST_CANCELLED],
        )

    def __str__(self) -> str:
        base = f"MCPError({self.code}): {self.message}"
        if self.data:
            base += f" {self.data}"
        return base

    def __repr__(self) -> str:
        return f"MCPError(code={self.code}, message={self.message!r}, data={self.data})"
