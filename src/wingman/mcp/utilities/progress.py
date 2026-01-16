"""Progress notification handler for MCP protocol."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from wingman.mcp.utilities.types import ProgressInfo

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = logging.getLogger(__name__)

# Type alias for progress callbacks
ProgressCallback = Callable[[ProgressInfo], Awaitable[None]]


class ProgressTracker:
    """
    Tracks progress state for active operations.

    Maintains history of progress updates for each token.
    """

    def __init__(self) -> None:
        """Initialize tracker."""
        self._active: dict[str | int, ProgressInfo] = {}
        self._completed: set[str | int] = set()

    def start_tracking(self, token: str | int) -> None:
        """
        Start tracking a progress token.

        Args:
            token: The progress token to track.
        """
        self._active[token] = ProgressInfo(progress_token=token, progress=0.0)
        self._completed.discard(token)

    def update(self, info: ProgressInfo) -> None:
        """
        Update progress for a token.

        Args:
            info: The progress info from notification.
        """
        self._active[info.progress_token] = info

        # Check if complete
        if info.is_complete:
            self._completed.add(info.progress_token)

    def is_complete(self, token: str | int) -> bool:
        """
        Check if operation is complete.

        Args:
            token: The progress token to check.

        Returns:
            True if operation completed.
        """
        return token in self._completed

    def get_progress(self, token: str | int) -> ProgressInfo | None:
        """
        Get current progress for token.

        Args:
            token: The progress token.

        Returns:
            Current progress info or None if not tracked.
        """
        return self._active.get(token)

    def remove(self, token: str | int) -> None:
        """
        Stop tracking a token.

        Args:
            token: The progress token to remove.
        """
        self._active.pop(token, None)
        self._completed.discard(token)

    def clear(self) -> None:
        """Clear all tracked progress."""
        self._active.clear()
        self._completed.clear()


class ProgressHandler:
    """
    Handles progress notifications from MCP server.

    Receives notifications/progress and dispatches to registered callbacks.
    This complements MCPClient.ProgressToken which sends progress to server.
    """

    def __init__(self) -> None:
        """Initialize progress handler."""
        self._token_callbacks: dict[str | int, list[ProgressCallback]] = {}
        self._global_callbacks: list[ProgressCallback] = []
        self._tracker = ProgressTracker()

    @property
    def tracker(self) -> ProgressTracker:
        """Access the progress tracker."""
        return self._tracker

    def on_progress(
        self,
        token: str | int,
        callback: ProgressCallback,
    ) -> None:
        """
        Register callback for specific progress token.

        Args:
            token: The progress token to listen for.
            callback: Async function to call with progress info.
        """
        if token not in self._token_callbacks:
            self._token_callbacks[token] = []
        self._token_callbacks[token].append(callback)
        self._tracker.start_tracking(token)

    def on_any_progress(self, callback: ProgressCallback) -> None:
        """
        Register global callback for all progress notifications.

        Args:
            callback: Async function to call with progress info.
        """
        self._global_callbacks.append(callback)

    def remove_callback(self, token: str | int, callback: ProgressCallback) -> None:
        """
        Remove a token-specific callback.

        Args:
            token: The progress token.
            callback: The callback to remove.
        """
        if token in self._token_callbacks:
            try:
                self._token_callbacks[token].remove(callback)
                if not self._token_callbacks[token]:
                    del self._token_callbacks[token]
            except ValueError:
                pass

    def remove_global_callback(self, callback: ProgressCallback) -> None:
        """
        Remove a global callback.

        Args:
            callback: The callback to remove.
        """
        try:
            self._global_callbacks.remove(callback)
        except ValueError:
            pass

    async def handle_progress(self, params: dict[str, Any] | None) -> None:
        """
        Handle notifications/progress from server.

        Args:
            params: Notification parameters.
        """
        if not params:
            logger.warning("Received progress notification without params")
            return

        try:
            info = ProgressInfo.from_dict(params)
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid progress notification: {e}")
            return

        logger.debug(
            f"Progress: token={info.progress_token}, "
            f"progress={info.progress}, total={info.total}"
        )

        # Update tracker
        self._tracker.update(info)

        # Invoke token-specific callbacks
        token_cbs = self._token_callbacks.get(info.progress_token, [])
        for callback in token_cbs:
            try:
                await callback(info)
            except Exception as e:
                logger.exception(f"Progress callback error: {e}")

        # Invoke global callbacks
        for callback in self._global_callbacks:
            try:
                await callback(info)
            except Exception as e:
                logger.exception(f"Global progress callback error: {e}")

    def register_handlers(self, client: "MCPClient") -> None:
        """
        Register progress notification handler with MCP client.

        Args:
            client: The MCP client to register with.
        """
        client.on_notification("notifications/progress", self.handle_progress)
        logger.debug("Registered progress notification handler")
