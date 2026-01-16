"""Ping utility for MCP connection health checks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = logging.getLogger(__name__)


class PingHandler:
    """
    Handles ping requests for connection health checks.

    Ping is bidirectional - both client and server can initiate.
    This handler responds to server-initiated pings.
    """

    async def handle_ping(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """
        Handle ping request from server.

        Args:
            params: Request parameters (should be empty or None).

        Returns:
            Empty result dict.
        """
        logger.debug("Received ping request")
        return {}

    def register_handlers(self, client: "MCPClient") -> None:
        """
        Register ping handler with MCP client.

        Args:
            client: The MCP client to register with.
        """
        client.on_request("ping", self.handle_ping)
        logger.debug("Registered ping handler")


async def ping_server(
    client: "MCPClient",
    timeout: float = 5.0,
) -> bool:
    """
    Ping the MCP server to check connection health.

    Args:
        client: The MCP client to use.
        timeout: Timeout in seconds for the ping request.

    Returns:
        True if server responded, False if timeout or error.
    """
    try:
        await client.request("ping", timeout=timeout)
        logger.debug("Ping successful")
        return True
    except Exception as e:
        logger.warning(f"Ping failed: {e}")
        return False


async def ping_with_retry(
    client: "MCPClient",
    retries: int = 3,
    timeout: float = 5.0,
    delay: float = 1.0,
) -> bool:
    """
    Ping server with retries.

    Args:
        client: The MCP client to use.
        retries: Number of retry attempts.
        timeout: Timeout per ping in seconds.
        delay: Delay between retries in seconds.

    Returns:
        True if any ping succeeded, False if all failed.
    """
    import asyncio

    for attempt in range(retries):
        if await ping_server(client, timeout):
            return True
        if attempt < retries - 1:
            logger.debug(f"Ping attempt {attempt + 1} failed, retrying...")
            await asyncio.sleep(delay)

    logger.warning(f"All {retries} ping attempts failed")
    return False
