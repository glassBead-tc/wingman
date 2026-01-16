"""
MCP Transport Layer.

Implements Streamable HTTP transport per MCP 2025-11-25 specification.
"""

from wingman.mcp.transport.types import TransportConfig, TransportEvent, TransportEventType
from wingman.mcp.transport.base import Transport, TransportError, ConnectionError, TimeoutError, SessionError
from wingman.mcp.transport.http import StreamableHTTPTransport

__all__ = [
    "Transport",
    "TransportConfig",
    "TransportEvent",
    "TransportEventType",
    "TransportError",
    "ConnectionError",
    "TimeoutError",
    "SessionError",
    "StreamableHTTPTransport",
]
