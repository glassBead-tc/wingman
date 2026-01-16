"""MCP protocol client implementation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from wingman.mcp.transport.base import Transport
from wingman.mcp.protocol.messages import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCNotification,
    is_request,
    is_notification,
    is_response,
)
from wingman.mcp.protocol.errors import (
    MCPError,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    REQUEST_TIMEOUT,
    REQUEST_CANCELLED,
)
from wingman.mcp.protocol.state import (
    ProtocolState,
    ProtocolStateMachine,
)

logger = logging.getLogger(__name__)

# Type aliases for handlers
RequestHandler = Callable[[dict[str, Any] | None], Awaitable[Any]]
NotificationHandler = Callable[[dict[str, Any] | None], Awaitable[None]]


@dataclass
class ProgressToken:
    """
    Token for tracking and reporting operation progress.

    Used by long-running operations to report progress back to the server.
    """

    token: str | int
    _client: "MCPClient"

    async def report(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        """
        Report progress to the server.

        Args:
            progress: Current progress value.
            total: Total value (if known).
            message: Optional progress message.
        """
        params: dict[str, Any] = {
            "progressToken": self.token,
            "progress": progress,
        }
        if total is not None:
            params["total"] = total
        if message is not None:
            params["message"] = message

        await self._client.notify("notifications/progress", params)


class MCPClient:
    """
    Core MCP protocol client.

    Handles JSON-RPC 2.0 message exchange, request/response correlation,
    server-initiated requests and notifications, and protocol lifecycle.
    """

    def __init__(
        self,
        transport: Transport,
        request_timeout: float = 60.0,
        max_pending_requests: int = 100,
    ):
        """
        Initialize MCP client.

        Args:
            transport: Transport layer for communication.
            request_timeout: Default timeout for requests in seconds.
            max_pending_requests: Maximum number of concurrent pending requests.
        """
        self.transport = transport
        self.request_timeout = request_timeout
        self.max_pending_requests = max_pending_requests

        self._state = ProtocolStateMachine()
        self._pending_requests: dict[str, asyncio.Future[Any]] = {}
        self._request_handlers: dict[str, RequestHandler] = {}
        self._notification_handlers: dict[str, NotificationHandler] = {}
        self._receive_task: asyncio.Task | None = None
        self._response_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._closing = False

    @property
    def state(self) -> ProtocolState:
        """Current protocol state."""
        return self._state.state

    @property
    def is_connected(self) -> bool:
        """Check if client is in a connected state."""
        return self._state.is_connected

    @property
    def is_ready(self) -> bool:
        """Check if client is ready for requests."""
        return self._state.is_ready

    @property
    def session_id(self) -> str | None:
        """Current session ID from transport."""
        return self.transport.session_id

    def on_state_change(
        self,
        callback: Callable[[ProtocolState, ProtocolState], None],
    ) -> None:
        """Register callback for state changes."""
        self._state.on_transition(callback)

    async def connect(self) -> None:
        """
        Connect transport and start message receiver.

        After connect(), the client is in INITIALIZING state.
        Call initialize() to complete handshake and reach READY state.
        """
        if self._state.state != ProtocolState.DISCONNECTED:
            raise MCPError(INTERNAL_ERROR, "Client already connected")

        self._closing = False
        self._state.transition(ProtocolState.CONNECTING)

        try:
            await self.transport.connect()
            self._receive_task = asyncio.create_task(
                self._receive_loop(),
                name="mcp-receive-loop",
            )
            self._state.transition(ProtocolState.INITIALIZING)
        except Exception as e:
            self._state.transition(ProtocolState.DISCONNECTED)
            raise MCPError(INTERNAL_ERROR, f"Connection failed: {e}")

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """
        Send a request and wait for the response.

        Args:
            method: The RPC method name.
            params: Optional method parameters.
            timeout: Request timeout (defaults to self.request_timeout).

        Returns:
            The result from the response.

        Raises:
            MCPError: On timeout, cancellation, or error response.
        """
        if not self._state.is_connected:
            raise MCPError(INTERNAL_ERROR, "Client not connected")

        if len(self._pending_requests) >= self.max_pending_requests:
            raise MCPError(INTERNAL_ERROR, "Too many pending requests")

        request = JSONRPCRequest(method=method, params=params)
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending_requests[request.id] = future

        effective_timeout = timeout if timeout is not None else self.request_timeout

        try:
            # Send the request
            immediate_response = await self.transport.send(request.to_dict())

            # If we got an immediate response, process it
            if immediate_response is not None:
                self._handle_response(immediate_response)

            # Wait for response
            result = await asyncio.wait_for(future, timeout=effective_timeout)
            return result

        except asyncio.TimeoutError:
            self._pending_requests.pop(request.id, None)
            raise MCPError.timeout(effective_timeout)

        except asyncio.CancelledError:
            self._pending_requests.pop(request.id, None)
            raise MCPError.cancelled("Request cancelled")

        finally:
            # Ensure cleanup
            self._pending_requests.pop(request.id, None)

    async def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """
        Send a notification (fire-and-forget).

        Args:
            method: The notification method name.
            params: Optional method parameters.
        """
        if not self._state.is_connected:
            raise MCPError(INTERNAL_ERROR, "Client not connected")

        notification = JSONRPCNotification(method=method, params=params)
        await self.transport.send(notification.to_dict())

    async def cancel_request(
        self,
        request_id: str,
        reason: str | None = None,
    ) -> None:
        """
        Cancel an in-flight request.

        Sends cancellation notification to server and completes the
        local future with a cancellation error.

        Args:
            request_id: ID of the request to cancel.
            reason: Optional reason for cancellation.
        """
        # Notify server
        await self.notify(
            "notifications/cancelled",
            {"requestId": request_id, "reason": reason},
        )

        # Cancel local future
        future = self._pending_requests.pop(request_id, None)
        if future and not future.done():
            future.set_exception(
                MCPError(REQUEST_CANCELLED, reason or "Request cancelled")
            )

    def on_request(self, method: str, handler: RequestHandler) -> None:
        """
        Register handler for server-initiated requests.

        Args:
            method: The method name to handle.
            handler: Async function receiving params, returning result.
        """
        self._request_handlers[method] = handler

    def on_notification(self, method: str, handler: NotificationHandler) -> None:
        """
        Register handler for server-initiated notifications.

        Args:
            method: The method name to handle.
            handler: Async function receiving params.
        """
        self._notification_handlers[method] = handler

    def create_progress_token(self, token: str | int) -> ProgressToken:
        """
        Create a progress token for reporting operation progress.

        Args:
            token: The progress token value from a request.

        Returns:
            ProgressToken instance for reporting progress.
        """
        return ProgressToken(token=token, _client=self)

    async def close(self) -> None:
        """Close connection and cleanup resources."""
        if self._closing:
            return

        self._closing = True

        # Transition state
        if self._state.state == ProtocolState.READY:
            self._state.transition(ProtocolState.CLOSING)
        elif self._state.state not in (ProtocolState.CLOSED, ProtocolState.DISCONNECTED):
            self._state.force_state(ProtocolState.CLOSING)

        # Cancel receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        # Cancel pending requests
        for request_id, future in list(self._pending_requests.items()):
            if not future.done():
                future.set_exception(MCPError.cancelled("Client closing"))
        self._pending_requests.clear()

        # Close transport
        await self.transport.disconnect()

        # Final state
        try:
            self._state.transition(ProtocolState.CLOSED)
        except Exception:
            self._state.force_state(ProtocolState.CLOSED)

    def mark_ready(self) -> None:
        """
        Mark the client as ready for normal operations.

        Called after successful capability negotiation.
        """
        if self._state.state == ProtocolState.INITIALIZING:
            self._state.transition(ProtocolState.READY)

    async def _receive_loop(self) -> None:
        """Background task processing incoming messages."""
        try:
            async for message in self.transport.receive():
                if self._closing:
                    break
                await self._handle_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
            if not self._closing:
                # Unexpected disconnect
                self._state.force_state(ProtocolState.DISCONNECTED)

    async def _handle_message(self, message: dict) -> None:
        """Route incoming message to appropriate handler."""
        try:
            if is_request(message):
                await self._handle_server_request(message)
            elif is_response(message):
                self._handle_response(message)
            elif is_notification(message):
                await self._handle_notification(message)
            else:
                logger.warning(f"Unknown message type: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _handle_response(self, message: dict) -> None:
        """Complete pending request future with response."""
        response = JSONRPCResponse.from_dict(message)
        request_id = str(response.id) if response.id is not None else None

        if request_id is None:
            logger.warning("Received response without id")
            return

        future = self._pending_requests.get(request_id)
        if future is None:
            logger.warning(f"No pending request for id: {request_id}")
            return

        if future.done():
            return

        if response.is_error:
            future.set_exception(MCPError.from_response(response.error.to_dict()))
        else:
            future.set_result(response.result)

    async def _handle_server_request(self, message: dict) -> None:
        """Handle request from server, send response."""
        request = JSONRPCRequest.from_dict(message)
        handler = self._request_handlers.get(request.method)

        if handler is None:
            # No handler registered
            response = JSONRPCResponse.error_response(
                id=request.id,
                code=METHOD_NOT_FOUND,
                message=f"Method not found: {request.method}",
            )
        else:
            try:
                result = await handler(request.params)
                response = JSONRPCResponse.success(id=request.id, result=result)
            except MCPError as e:
                response = JSONRPCResponse.error_response(
                    id=request.id,
                    code=e.code,
                    message=e.message,
                    data=e.data,
                )
            except Exception as e:
                logger.exception(f"Handler error for {request.method}")
                response = JSONRPCResponse.error_response(
                    id=request.id,
                    code=INTERNAL_ERROR,
                    message=str(e),
                )

        await self.transport.send(response.to_dict())

    async def _handle_notification(self, message: dict) -> None:
        """Handle notification from server."""
        notification = JSONRPCNotification.from_dict(message)
        handler = self._notification_handlers.get(notification.method)

        if handler is not None:
            try:
                await handler(notification.params)
            except Exception as e:
                logger.exception(f"Notification handler error for {notification.method}: {e}")

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
