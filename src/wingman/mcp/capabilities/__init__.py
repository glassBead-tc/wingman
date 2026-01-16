"""
MCP Capability Negotiation.

Handles the initialization handshake between client and server,
exchanging capability declarations.
"""

from wingman.mcp.capabilities.client import (
    ClientCapabilities,
    SamplingCapability,
    RootsCapability,
    ElicitationCapability,
    TasksCapability,
    DEFAULT_CLIENT_CAPABILITIES,
)
from wingman.mcp.capabilities.server import (
    ServerCapabilities,
    ServerToolsCapability,
    ServerResourcesCapability,
    ServerPromptsCapability,
    ServerTasksCapability,
)
from wingman.mcp.capabilities.negotiation import (
    CapabilityNegotiator,
    NegotiationResult,
    ClientInfo,
    ServerInfo,
    IncompatibleProtocolError,
    PROTOCOL_VERSION,
    SUPPORTED_VERSIONS,
)

__all__ = [
    # Client capabilities
    "ClientCapabilities",
    "SamplingCapability",
    "RootsCapability",
    "ElicitationCapability",
    "TasksCapability",
    "DEFAULT_CLIENT_CAPABILITIES",
    # Server capabilities
    "ServerCapabilities",
    "ServerToolsCapability",
    "ServerResourcesCapability",
    "ServerPromptsCapability",
    "ServerTasksCapability",
    # Negotiation
    "CapabilityNegotiator",
    "NegotiationResult",
    "ClientInfo",
    "ServerInfo",
    "IncompatibleProtocolError",
    "PROTOCOL_VERSION",
    "SUPPORTED_VERSIONS",
]
