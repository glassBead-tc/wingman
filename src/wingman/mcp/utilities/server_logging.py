"""Logging utility for MCP server log messages."""

from __future__ import annotations

import logging as python_logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from wingman.mcp.utilities.types import LogLevel, LogMessage

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = python_logging.getLogger(__name__)

# Type alias for log message callbacks
LogMessageCallback = Callable[[LogMessage], Awaitable[None]]

# Mapping from MCP log levels to Python logging levels
MCP_TO_PYTHON_LEVEL: dict[LogLevel, int] = {
    LogLevel.DEBUG: python_logging.DEBUG,
    LogLevel.INFO: python_logging.INFO,
    LogLevel.NOTICE: python_logging.INFO,  # Python has no NOTICE
    LogLevel.WARNING: python_logging.WARNING,
    LogLevel.ERROR: python_logging.ERROR,
    LogLevel.CRITICAL: python_logging.CRITICAL,
    LogLevel.ALERT: python_logging.CRITICAL,  # Map to CRITICAL
    LogLevel.EMERGENCY: python_logging.CRITICAL,  # Map to CRITICAL
}


@dataclass
class LoggingConfig:
    """Configuration for MCP logging handler."""

    default_level: LogLevel = LogLevel.INFO
    """Default log level for server."""

    forward_to_python: bool = True
    """Forward MCP log messages to Python logging."""

    python_logger_prefix: str = "mcp.server"
    """Prefix for Python logger names when forwarding."""

    min_level: LogLevel | None = None
    """Minimum level to process (filter lower levels)."""


@dataclass
class LoggingState:
    """State tracking for logging operations."""

    current_level: LogLevel = LogLevel.INFO
    """Currently set server log level."""

    message_count: int = 0
    """Count of messages received."""

    level_counts: dict[LogLevel, int] = field(default_factory=dict)
    """Count of messages by level."""


class LoggingHandler:
    """
    Handles MCP logging feature.

    - logging/setLevel: Client sets server's log level
    - notifications/message: Server sends log messages to client

    This allows clients to control server logging verbosity and
    receive structured log output from the server.
    """

    def __init__(self, config: LoggingConfig | None = None) -> None:
        """
        Initialize logging handler.

        Args:
            config: Optional configuration.
        """
        self.config = config or LoggingConfig()
        self._state = LoggingState(current_level=self.config.default_level)
        self._callbacks: list[LogMessageCallback] = []

    @property
    def state(self) -> LoggingState:
        """Access logging state."""
        return self._state

    @property
    def current_level(self) -> LogLevel:
        """Get currently set server log level."""
        return self._state.current_level

    def on_log_message(self, callback: LogMessageCallback) -> None:
        """
        Register callback for log messages from server.

        Args:
            callback: Async function to call with log message.
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: LogMessageCallback) -> None:
        """
        Remove a log message callback.

        Args:
            callback: The callback to remove.
        """
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    async def handle_log_message(self, params: dict[str, Any] | None) -> None:
        """
        Handle notifications/message from server.

        Args:
            params: Notification parameters.
        """
        if not params:
            logger.warning("Received log notification without params")
            return

        try:
            message = LogMessage.from_dict(params)
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid log notification: {e}")
            return

        # Update stats
        self._state.message_count += 1
        self._state.level_counts[message.level] = (
            self._state.level_counts.get(message.level, 0) + 1
        )

        # Check minimum level filter
        if self.config.min_level is not None:
            if message.level < self.config.min_level:
                return

        logger.debug(
            f"Server log: level={message.level.value}, "
            f"logger={message.logger}, data={message.data}"
        )

        # Forward to Python logging if enabled
        if self.config.forward_to_python:
            self._forward_to_python(message)

        # Invoke callbacks
        for callback in self._callbacks:
            try:
                await callback(message)
            except Exception as e:
                logger.exception(f"Log message callback error: {e}")

    def _forward_to_python(self, message: LogMessage) -> None:
        """
        Forward MCP log message to Python logging.

        Args:
            message: The log message to forward.
        """
        # Determine logger name
        if message.logger:
            logger_name = f"{self.config.python_logger_prefix}.{message.logger}"
        else:
            logger_name = self.config.python_logger_prefix

        # Get Python log level
        py_level = MCP_TO_PYTHON_LEVEL.get(message.level, python_logging.INFO)

        # Format message data
        if isinstance(message.data, str):
            log_msg = message.data
        elif message.data is not None:
            log_msg = f"{message.data}"
        else:
            log_msg = "(no message)"

        # Log it
        python_logging.getLogger(logger_name).log(py_level, log_msg)

    def register_handlers(self, client: "MCPClient") -> None:
        """
        Register logging notification handler with MCP client.

        Args:
            client: The MCP client to register with.
        """
        client.on_notification("notifications/message", self.handle_log_message)
        logger.debug("Registered logging notification handler")


async def set_server_log_level(
    client: "MCPClient",
    level: LogLevel,
    handler: LoggingHandler | None = None,
) -> None:
    """
    Request server to change its logging level.

    Args:
        client: The MCP client to use.
        level: The log level to set.
        handler: Optional handler to update state.

    Raises:
        MCPError: If server returns an error.
    """
    logger.info(f"Setting server log level to: {level.value}")

    await client.request("logging/setLevel", {"level": level.value})

    # Update handler state if provided
    if handler is not None:
        handler._state.current_level = level


async def get_server_log_level(handler: LoggingHandler) -> LogLevel:
    """
    Get the currently set server log level.

    Note: This returns the last level we set, not querying the server.

    Args:
        handler: The logging handler.

    Returns:
        Current log level.
    """
    return handler.current_level
