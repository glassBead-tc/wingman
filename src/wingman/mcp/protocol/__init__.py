"""
MCP Protocol Core.

Implements JSON-RPC 2.0 message framing, request/response correlation,
and the protocol state machine.
"""

from wingman.mcp.protocol.messages import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCNotification,
    JSONRPCError,
)
from wingman.mcp.protocol.errors import (
    MCPError,
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    REQUEST_TIMEOUT,
    REQUEST_CANCELLED,
    SESSION_EXPIRED,
)
from wingman.mcp.protocol.state import (
    ProtocolState,
    ProtocolStateMachine,
    InvalidStateTransition,
)
from wingman.mcp.protocol.client import MCPClient, ProgressToken

__all__ = [
    # Messages
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCNotification",
    "JSONRPCError",
    # Errors
    "MCPError",
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "REQUEST_TIMEOUT",
    "REQUEST_CANCELLED",
    "SESSION_EXPIRED",
    # State
    "ProtocolState",
    "ProtocolStateMachine",
    "InvalidStateTransition",
    # Client
    "MCPClient",
    "ProgressToken",
]
