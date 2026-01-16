"""Cancellation utility for MCP request cancellation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from wingman.mcp.utilities.types import CancellationInfo

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = logging.getLogger(__name__)

# Type alias for cancellation callbacks
CancellationCallback = Callable[[CancellationInfo], Awaitable[None]]


class CancellationError(Exception):
    """Error related to cancellation operations."""

    pass


class CancellationHandler:
    """
    Handles cancellation notifications from MCP server.

    Receives notifications/cancelled when server cancels a request.
    This complements MCPClient.cancel_request() which sends cancellation to server.
    """

    def __init__(self) -> None:
        """Initialize cancellation handler."""
        self._callbacks: list[CancellationCallback] = []
        self._request_callbacks: dict[str, list[CancellationCallback]] = {}

    def on_cancelled(self, callback: CancellationCallback) -> None:
        """
        Register global callback for cancellation notifications.

        Args:
            callback: Async function to call with cancellation info.
        """
        self._callbacks.append(callback)

    def on_request_cancelled(
        self,
        request_id: str,
        callback: CancellationCallback,
    ) -> None:
        """
        Register callback for specific request cancellation.

        Args:
            request_id: The request ID to listen for.
            callback: Async function to call if this request is cancelled.
        """
        if request_id not in self._request_callbacks:
            self._request_callbacks[request_id] = []
        self._request_callbacks[request_id].append(callback)

    def remove_callback(self, callback: CancellationCallback) -> None:
        """
        Remove a global callback.

        Args:
            callback: The callback to remove.
        """
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def remove_request_callback(
        self,
        request_id: str,
        callback: CancellationCallback | None = None,
    ) -> None:
        """
        Remove callbacks for a specific request.

        Args:
            request_id: The request ID.
            callback: Specific callback to remove, or None to remove all.
        """
        if request_id not in self._request_callbacks:
            return

        if callback is None:
            del self._request_callbacks[request_id]
        else:
            try:
                self._request_callbacks[request_id].remove(callback)
                if not self._request_callbacks[request_id]:
                    del self._request_callbacks[request_id]
            except ValueError:
                pass

    async def handle_cancelled(self, params: dict[str, Any] | None) -> None:
        """
        Handle notifications/cancelled from server.

        Args:
            params: Notification parameters.
        """
        if not params:
            logger.warning("Received cancellation notification without params")
            return

        try:
            info = CancellationInfo.from_dict(params)
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid cancellation notification: {e}")
            return

        logger.info(
            f"Request cancelled: id={info.request_id}, reason={info.reason}"
        )

        # Invoke request-specific callbacks
        request_cbs = self._request_callbacks.get(info.request_id, [])
        for callback in request_cbs:
            try:
                await callback(info)
            except Exception as e:
                logger.exception(f"Cancellation callback error: {e}")

        # Clean up request callbacks after invocation
        self._request_callbacks.pop(info.request_id, None)

        # Invoke global callbacks
        for callback in self._callbacks:
            try:
                await callback(info)
            except Exception as e:
                logger.exception(f"Global cancellation callback error: {e}")

    def register_handlers(self, client: "MCPClient") -> None:
        """
        Register cancellation notification handler with MCP client.

        Args:
            client: The MCP client to register with.
        """
        client.on_notification("notifications/cancelled", self.handle_cancelled)
        logger.debug("Registered cancellation notification handler")


async def cancel_server_request(
    client: "MCPClient",
    request_id: str,
    reason: str | None = None,
) -> None:
    """
    Send cancellation notification to server.

    Note: Cannot cancel 'initialize' request per MCP spec.

    Args:
        client: The MCP client to use.
        request_id: ID of the request to cancel.
        reason: Optional reason for cancellation.

    Raises:
        CancellationError: If trying to cancel 'initialize'.
    """
    # Per MCP spec, cannot cancel initialize request
    if request_id == "initialize":
        raise CancellationError("Cannot cancel initialize request")

    logger.info(f"Cancelling request: id={request_id}, reason={reason}")

    params: dict[str, Any] = {"requestId": request_id}
    if reason is not None:
        params["reason"] = reason

    await client.notify("notifications/cancelled", params)
