"""JSON-RPC 2.0 message types for MCP protocol."""

from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass
class JSONRPCRequest:
    """
    JSON-RPC 2.0 request message.

    Requests expect a response from the recipient.
    """

    method: str
    params: dict[str, Any] | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    jsonrpc: str = field(default="2.0", init=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        msg: dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "id": self.id,
        }
        if self.params is not None:
            msg["params"] = self.params
        return msg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JSONRPCRequest":
        """Create from JSON dict."""
        return cls(
            method=data["method"],
            params=data.get("params"),
            id=data.get("id", str(uuid.uuid4())),
        )

    def __str__(self) -> str:
        return f"Request({self.method}, id={self.id})"


@dataclass
class JSONRPCError:
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            error["data"] = self.data
        return error

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JSONRPCError":
        """Create from JSON dict."""
        return cls(
            code=data.get("code", -32603),
            message=data.get("message", "Unknown error"),
            data=data.get("data"),
        )


@dataclass
class JSONRPCResponse:
    """
    JSON-RPC 2.0 response message.

    Either result or error must be present, but not both.
    """

    id: str | int | None
    result: Any = None
    error: JSONRPCError | None = None
    jsonrpc: str = field(default="2.0", init=False)

    @property
    def is_error(self) -> bool:
        """Check if this is an error response."""
        return self.error is not None

    @property
    def is_success(self) -> bool:
        """Check if this is a success response."""
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        msg: dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
        }
        if self.error is not None:
            msg["error"] = self.error.to_dict()
        else:
            msg["result"] = self.result
        return msg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JSONRPCResponse":
        """Create from JSON dict."""
        error = None
        if "error" in data:
            error = JSONRPCError.from_dict(data["error"])
        return cls(
            id=data.get("id"),
            result=data.get("result"),
            error=error,
        )

    @classmethod
    def success(cls, id: str | int | None, result: Any = None) -> "JSONRPCResponse":
        """Create a success response."""
        return cls(id=id, result=result)

    @classmethod
    def error_response(
        cls,
        id: str | int | None,
        code: int,
        message: str,
        data: Any = None,
    ) -> "JSONRPCResponse":
        """Create an error response."""
        return cls(id=id, error=JSONRPCError(code=code, message=message, data=data))

    def __str__(self) -> str:
        if self.is_error:
            return f"Response(id={self.id}, error={self.error.code})"
        return f"Response(id={self.id}, success)"


@dataclass
class JSONRPCNotification:
    """
    JSON-RPC 2.0 notification message.

    Notifications do not expect a response (no id field).
    """

    method: str
    params: dict[str, Any] | None = None
    jsonrpc: str = field(default="2.0", init=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        msg: dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.params is not None:
            msg["params"] = self.params
        return msg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JSONRPCNotification":
        """Create from JSON dict."""
        return cls(
            method=data["method"],
            params=data.get("params"),
        )

    def __str__(self) -> str:
        return f"Notification({self.method})"


def parse_message(data: dict[str, Any]) -> JSONRPCRequest | JSONRPCResponse | JSONRPCNotification:
    """
    Parse a JSON dict into the appropriate message type.

    Args:
        data: JSON-RPC message dict.

    Returns:
        The appropriate message type based on content.

    Raises:
        ValueError: If the message is malformed.
    """
    if data.get("jsonrpc") != "2.0":
        raise ValueError("Invalid JSON-RPC version")

    has_id = "id" in data
    has_method = "method" in data
    has_result = "result" in data
    has_error = "error" in data

    if has_method and has_id:
        # Request
        return JSONRPCRequest.from_dict(data)
    elif has_method and not has_id:
        # Notification
        return JSONRPCNotification.from_dict(data)
    elif (has_result or has_error) and has_id:
        # Response
        return JSONRPCResponse.from_dict(data)
    else:
        raise ValueError("Cannot determine message type")


def is_request(data: dict[str, Any]) -> bool:
    """Check if message is a request (has id and method)."""
    return "id" in data and "method" in data


def is_notification(data: dict[str, Any]) -> bool:
    """Check if message is a notification (has method, no id)."""
    return "method" in data and "id" not in data


def is_response(data: dict[str, Any]) -> bool:
    """Check if message is a response (has id, no method)."""
    return "id" in data and "method" not in data
