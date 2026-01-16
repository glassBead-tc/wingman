"""Abstract base transport and error types."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Callable

from wingman.mcp.transport.types import TransportConfig, TransportEvent


class TransportError(Exception):
    """Base exception for transport errors."""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class ConnectionError(TransportError):
    """Failed to establish connection to server."""

    pass


class TimeoutError(TransportError):
    """Request or connection timed out."""

    pass


class SessionError(TransportError):
    """Session-related error (expired, invalid, not established)."""

    pass


class Transport(ABC):
    """
    Abstract base class for MCP transports.

    Transports handle the low-level communication with MCP servers,
    including connection management, message serialization, and
    bidirectional message exchange.
    """

    def __init__(self, config: TransportConfig):
        self.config = config
        self._event_handlers: list[Callable[[TransportEvent], None]] = []

    def on_event(self, handler: Callable[[TransportEvent], None]) -> None:
        """
        Register an event handler for transport events.

        Args:
            handler: Callback invoked when transport events occur.
        """
        self._event_handlers.append(handler)

    def _emit_event(self, event: TransportEvent) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception:
                # Don't let handler errors affect transport
                pass

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to the MCP server.

        Raises:
            ConnectionError: If connection cannot be established.
            TimeoutError: If connection times out.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection and release all resources.

        This method should be safe to call multiple times.
        """
        pass

    @abstractmethod
    async def send(self, message: dict) -> dict | None:
        """
        Send a JSON-RPC message to the server.

        For requests that receive immediate responses (non-SSE), the
        response is returned directly. For SSE-upgraded responses,
        returns None and responses arrive via receive().

        Args:
            message: JSON-RPC message (request, notification, or response).

        Returns:
            Immediate response dict, or None if SSE-upgraded.

        Raises:
            TransportError: If send fails.
            SessionError: If session is invalid or not established.
        """
        pass

    @abstractmethod
    def receive(self) -> AsyncIterator[dict]:
        """
        Async iterator yielding JSON-RPC messages from the server.

        This includes:
        - SSE stream messages
        - Server-initiated requests/notifications
        - Queued responses from send() calls

        Yields:
            JSON-RPC message dicts.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if transport is currently connected.

        Returns:
            True if connected and ready for communication.
        """
        pass

    @property
    @abstractmethod
    def session_id(self) -> str | None:
        """
        Current MCP session ID, if established.

        The session ID is set by the server during initial connection
        and must be included in all subsequent requests.

        Returns:
            Session ID string, or None if not yet established.
        """
        pass

    async def __aenter__(self) -> "Transport":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
