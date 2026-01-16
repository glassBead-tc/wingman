"""
MCP protocol utilities for bidirectional communication.

This module provides utilities for the MCP 2025-11-25 specification:
- Ping: Connection health checks
- Progress: Long-running operation tracking
- Cancellation: Request cancellation handling
- Logging: Server log message handling
- Completion: Argument autocompletion
- Pagination: Cursor-based list pagination
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

# Types
from wingman.mcp.utilities.types import (
    LogLevel,
    ProgressInfo,
    LogMessage,
    CancellationInfo,
    CompletionRef,
    CompletionArgument,
    CompletionRequest,
    CompletionResponse,
    PaginatedResult,
)

# Ping
from wingman.mcp.utilities.ping import (
    PingHandler,
    ping_server,
    ping_with_retry,
)

# Progress
from wingman.mcp.utilities.progress import (
    ProgressHandler,
    ProgressTracker,
    ProgressCallback,
)

# Cancellation
from wingman.mcp.utilities.cancellation import (
    CancellationHandler,
    CancellationCallback,
    CancellationError,
    cancel_server_request,
)

# Logging
from wingman.mcp.utilities.server_logging import (
    LoggingHandler,
    LoggingConfig,
    LoggingState,
    LogMessageCallback,
    set_server_log_level,
    get_server_log_level,
)

# Completion
from wingman.mcp.utilities.completion import (
    CompletionHandler,
    CompletionError,
    CompletionNotSupportedError,
    complete_argument,
)

# Pagination
from wingman.mcp.utilities.pagination import (
    PaginatedListHelper,
    PaginationError,
    InvalidCursorError,
    list_tools_paginated,
    list_all_tools,
    list_resources_paginated,
    list_all_resources,
    list_prompts_paginated,
    list_all_prompts,
    list_resource_templates_paginated,
    list_all_resource_templates,
)

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient
    from wingman.mcp.capabilities.server import ServerCapabilities

logger = logging.getLogger(__name__)

__all__ = [
    # Types
    "LogLevel",
    "ProgressInfo",
    "LogMessage",
    "CancellationInfo",
    "CompletionRef",
    "CompletionArgument",
    "CompletionRequest",
    "CompletionResponse",
    "PaginatedResult",
    # Ping
    "PingHandler",
    "ping_server",
    "ping_with_retry",
    # Progress
    "ProgressHandler",
    "ProgressTracker",
    "ProgressCallback",
    # Cancellation
    "CancellationHandler",
    "CancellationCallback",
    "CancellationError",
    "cancel_server_request",
    # Logging
    "LoggingHandler",
    "LoggingConfig",
    "LoggingState",
    "LogMessageCallback",
    "set_server_log_level",
    "get_server_log_level",
    # Completion
    "CompletionHandler",
    "CompletionError",
    "CompletionNotSupportedError",
    "complete_argument",
    # Pagination
    "PaginatedListHelper",
    "PaginationError",
    "InvalidCursorError",
    "list_tools_paginated",
    "list_all_tools",
    "list_resources_paginated",
    "list_all_resources",
    "list_prompts_paginated",
    "list_all_prompts",
    "list_resource_templates_paginated",
    "list_all_resource_templates",
    # Setup
    "setup_utility_handlers",
    "UtilityHandlers",
]


class UtilityHandlers:
    """
    Container for all utility handlers.

    Provides easy access to registered utility handlers.
    """

    def __init__(
        self,
        ping: PingHandler,
        progress: ProgressHandler,
        cancellation: CancellationHandler,
        logging: LoggingHandler | None = None,
    ) -> None:
        """
        Initialize utility handlers container.

        Args:
            ping: Ping handler.
            progress: Progress notification handler.
            cancellation: Cancellation notification handler.
            logging: Logging handler (if server supports it).
        """
        self.ping = ping
        self.progress = progress
        self.cancellation = cancellation
        self.logging = logging


async def setup_utility_handlers(
    client: "MCPClient",
    server_capabilities: "ServerCapabilities | None" = None,
    logging_config: LoggingConfig | None = None,
) -> UtilityHandlers:
    """
    Set up all utility handlers for an MCP client.

    Registers handlers for ping, progress, cancellation, and logging
    based on server capabilities.

    Args:
        client: The MCP client to register handlers with.
        server_capabilities: Server capabilities to check for logging support.
        logging_config: Optional logging configuration.

    Returns:
        UtilityHandlers container with all registered handlers.
    """
    logger.debug("Setting up utility handlers")

    # Ping - always available (bidirectional)
    ping_handler = PingHandler()
    ping_handler.register_handlers(client)

    # Progress - always available (server → client notifications)
    progress_handler = ProgressHandler()
    progress_handler.register_handlers(client)

    # Cancellation - always available (bidirectional)
    cancellation_handler = CancellationHandler()
    cancellation_handler.register_handlers(client)

    # Logging - only if server supports it
    logging_handler: LoggingHandler | None = None
    if server_capabilities is not None and server_capabilities.logging:
        logging_handler = LoggingHandler(logging_config)
        logging_handler.register_handlers(client)
        logger.debug("Registered logging handler (server supports logging)")
    else:
        logger.debug("Skipping logging handler (server doesn't support logging)")

    logger.info("Utility handlers setup complete")

    return UtilityHandlers(
        ping=ping_handler,
        progress=progress_handler,
        cancellation=cancellation_handler,
        logging=logging_handler,
    )
