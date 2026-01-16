"""MCP capability negotiation protocol."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wingman.mcp.capabilities.client import (
    ClientCapabilities,
    DEFAULT_CLIENT_CAPABILITIES,
)
from wingman.mcp.capabilities.server import ServerCapabilities

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = logging.getLogger(__name__)

# Protocol version constants
PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_VERSIONS = ["2025-11-25", "2024-11-05"]


class IncompatibleProtocolError(Exception):
    """Server protocol version is not compatible with client."""

    def __init__(self, message: str, server_version: str | None = None):
        super().__init__(message)
        self.server_version = server_version


@dataclass
class ClientInfo:
    """Information about this client sent during initialization."""

    name: str = "wingman"
    version: str = "0.5.0"

    def to_dict(self) -> dict[str, str]:
        """Convert to wire format."""
        return {"name": self.name, "version": self.version}


@dataclass
class ServerInfo:
    """Information about the connected server."""

    name: str
    version: str

    @classmethod
    def from_dict(cls, data: dict) -> "ServerInfo":
        """Create from server response."""
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "unknown"),
        )

    def to_dict(self) -> dict[str, str]:
        """Convert to dict."""
        return {"name": self.name, "version": self.version}


@dataclass
class NegotiationResult:
    """
    Result of successful capability negotiation.

    Contains all information exchanged during the initialize handshake.
    """

    protocol_version: str
    """Negotiated protocol version."""

    server_info: ServerInfo
    """Information about the server."""

    server_capabilities: ServerCapabilities
    """Capabilities declared by the server."""

    client_capabilities: ClientCapabilities
    """Capabilities declared by the client."""

    def __str__(self) -> str:
        features = self.server_capabilities.get_available_features()
        return (
            f"NegotiationResult(version={self.protocol_version}, "
            f"server={self.server_info.name}/{self.server_info.version}, "
            f"features={features})"
        )


class CapabilityNegotiator:
    """
    Handles MCP initialization handshake.

    Performs the initialize/initialized exchange to negotiate
    capabilities between client and server.
    """

    def __init__(
        self,
        client: "MCPClient",
        client_capabilities: ClientCapabilities | None = None,
        client_info: ClientInfo | None = None,
    ):
        """
        Initialize the negotiator.

        Args:
            client: The MCP client to use for communication.
            client_capabilities: Capabilities to declare (defaults to full support).
            client_info: Client information (defaults to wingman).
        """
        self.client = client
        self.client_capabilities = client_capabilities or DEFAULT_CLIENT_CAPABILITIES
        self.client_info = client_info or ClientInfo()
        self._result: NegotiationResult | None = None

    @property
    def result(self) -> NegotiationResult | None:
        """
        Get negotiation result.

        Returns:
            NegotiationResult if negotiation completed, None otherwise.
        """
        return self._result

    @property
    def is_negotiated(self) -> bool:
        """Check if negotiation has completed successfully."""
        return self._result is not None

    async def negotiate(self, timeout: float = 10.0) -> NegotiationResult:
        """
        Perform the initialization handshake.

        Sends initialize request with client capabilities,
        validates server response, and sends initialized notification.

        Args:
            timeout: Timeout for the initialize request.

        Returns:
            NegotiationResult with server capabilities.

        Raises:
            IncompatibleProtocolError: If server version not supported.
            MCPError: If initialization fails.
        """
        logger.debug(
            f"Starting capability negotiation with {self.client_info.name}"
        )

        # Build initialize request
        init_params = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": self.client_capabilities.to_dict(),
            "clientInfo": self.client_info.to_dict(),
        }

        # Send initialize request
        response = await self.client.request(
            "initialize",
            init_params,
            timeout=timeout,
        )

        # Validate protocol version
        server_version = response.get("protocolVersion", "")
        if server_version not in SUPPORTED_VERSIONS:
            raise IncompatibleProtocolError(
                f"Server protocol version '{server_version}' not supported. "
                f"Supported versions: {SUPPORTED_VERSIONS}",
                server_version=server_version,
            )

        logger.debug(f"Server responded with protocol version: {server_version}")

        # Parse server info
        server_info = ServerInfo.from_dict(response.get("serverInfo", {}))
        logger.info(f"Connected to server: {server_info.name} v{server_info.version}")

        # Parse server capabilities
        server_capabilities = ServerCapabilities.from_dict(
            response.get("capabilities", {})
        )

        features = server_capabilities.get_available_features()
        logger.info(f"Server capabilities: {features}")

        # Send initialized notification to complete handshake
        await self.client.notify("initialized")
        logger.debug("Sent initialized notification")

        # Mark client as ready
        self.client.mark_ready()

        # Store and return result
        self._result = NegotiationResult(
            protocol_version=server_version,
            server_info=server_info,
            server_capabilities=server_capabilities,
            client_capabilities=self.client_capabilities,
        )

        return self._result

    def check_capability(self, capability: str) -> bool:
        """
        Check if a specific capability was negotiated.

        Args:
            capability: Capability name ('tools', 'resources', etc.)

        Returns:
            True if capability is available.
        """
        if self._result is None:
            return False

        return capability in self._result.server_capabilities.get_available_features()


async def negotiate_capabilities(
    client: "MCPClient",
    client_capabilities: ClientCapabilities | None = None,
    client_info: ClientInfo | None = None,
    timeout: float = 10.0,
) -> NegotiationResult:
    """
    Convenience function for capability negotiation.

    Args:
        client: The MCP client (should be connected but not initialized).
        client_capabilities: Capabilities to declare.
        client_info: Client information.
        timeout: Initialization timeout.

    Returns:
        NegotiationResult with server capabilities.
    """
    negotiator = CapabilityNegotiator(
        client=client,
        client_capabilities=client_capabilities,
        client_info=client_info,
    )
    return await negotiator.negotiate(timeout=timeout)
