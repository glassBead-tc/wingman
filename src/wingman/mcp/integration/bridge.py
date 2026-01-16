"""Hybrid SDK-MCP bridge for coordinated operation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from wingman.mcp.transport import StreamableHTTPTransport, TransportConfig
from wingman.mcp.protocol import MCPClient
from wingman.mcp.capabilities import (
    ClientCapabilities,
    DEFAULT_CLIENT_CAPABILITIES,
    CapabilityNegotiator,
    NegotiationResult,
)
from wingman.mcp.config import MCPServerConfig
from wingman.mcp.integration.llm_adapter import DedalusLLMAdapter, LLMInterface
from wingman.mcp.integration.server_registry import ServerRegistry, ServerInfo
from wingman.mcp.utilities import (
    setup_utility_handlers,
    UtilityHandlers,
    LoggingConfig,
)

if TYPE_CHECKING:
    from dedalus_labs import AsyncDedalus

logger = logging.getLogger(__name__)


def mcp_tool_to_openai(mcp_tool: dict[str, Any]) -> dict[str, Any]:
    """
    Convert MCP tool schema to OpenAI/Anthropic function calling format.

    MCP format:
        {"name": "...", "description": "...", "inputSchema": {...}}

    OpenAI/Anthropic format:
        {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    return {
        "type": "function",
        "function": {
            "name": mcp_tool["name"],
            "description": mcp_tool.get("description", ""),
            "parameters": mcp_tool.get("inputSchema", {"type": "object", "properties": {}}),
        },
    }


# Type for approval callbacks
ApprovalCallback = Callable[[Any], Awaitable[tuple[bool, Any | None]]]


@dataclass
class HybridConfig:
    """Configuration for hybrid SDK+MCP operation."""

    # SDK settings
    dedalus_client: "AsyncDedalus | None" = None
    """Optional Dedalus SDK client for LLM operations."""

    # MCP settings
    mcp_servers: list[str] = field(default_factory=list)
    """List of MCP server URLs to connect to (legacy, no auth)."""

    server_configs: dict[str, MCPServerConfig] = field(default_factory=dict)
    """MCP server configs with authentication (name -> config)."""

    client_capabilities: ClientCapabilities = field(
        default_factory=lambda: DEFAULT_CLIENT_CAPABILITIES
    )
    """Client capabilities to declare during negotiation."""

    # Feature settings
    enable_tasks: bool = True
    """Whether to enable task-based execution."""

    enable_sampling: bool = True
    """Whether to enable server-initiated sampling."""

    enable_elicitation: bool = True
    """Whether to enable user input elicitation."""

    # Connection settings
    connect_timeout: float = 10.0
    """Timeout for server connections."""

    request_timeout: float = 60.0
    """Default timeout for requests."""

    auto_reconnect: bool = False
    """Whether to automatically reconnect on disconnect."""

    # Panel awareness (ARCH-007 fix)
    panel_id: str | None = None
    """Optional panel ID for multi-panel state isolation."""

    # Utility settings
    logging_config: LoggingConfig | None = None
    """Configuration for MCP server logging handler."""


@dataclass
class ConnectedServer:
    """A connected MCP server with its client and negotiation result."""

    url: str
    client: MCPClient
    transport: StreamableHTTPTransport
    negotiation: NegotiationResult
    utilities: UtilityHandlers | None = None
    """Utility handlers for this connection."""


class HybridMCPBridge:
    """
    Bridges Dedalus SDK with direct MCP clients for hybrid operation.

    Manages connections to multiple MCP servers, coordinates feature
    handlers, and provides a unified interface for MCP operations.
    """

    def __init__(
        self,
        config: HybridConfig,
        approval_callback: ApprovalCallback | None = None,
    ):
        """
        Initialize the hybrid bridge.

        Args:
            config: Bridge configuration.
            approval_callback: Callback for handling approval requests.
        """
        self.config = config
        self._approval_callback = approval_callback

        # Core components
        self._dedalus: "AsyncDedalus | None" = config.dedalus_client
        self._llm_adapter: DedalusLLMAdapter | None = None
        self._server_registry = ServerRegistry()
        self._connected_servers: dict[str, ConnectedServer] = {}

        # State
        self._initialized = False
        self._shutting_down = False
        self._lock = asyncio.Lock()

    @property
    def llm_adapter(self) -> LLMInterface | None:
        """Get the LLM adapter for chat completions."""
        return self._llm_adapter

    @property
    def server_registry(self) -> ServerRegistry:
        """Get the server registry."""
        return self._server_registry

    @property
    def is_initialized(self) -> bool:
        """Check if bridge is initialized."""
        return self._initialized

    async def initialize(self) -> None:
        """
        Initialize the hybrid bridge.

        Sets up LLM adapter and connects to configured MCP servers.
        """
        async with self._lock:
            if self._initialized:
                return

            logger.info("Initializing hybrid MCP bridge")

            # Set up LLM adapter if Dedalus client provided
            if self._dedalus:
                self._llm_adapter = DedalusLLMAdapter(self._dedalus)
                logger.debug("LLM adapter initialized")

            # Connect to configured MCP servers (legacy URL-only)
            for server_url in self.config.mcp_servers:
                try:
                    await self._connect_server(server_url)
                except Exception as e:
                    logger.error(f"Failed to connect to {server_url}: {e}")
                    # Continue with other servers

            # Connect to servers with auth configs
            for name, server_config in self.config.server_configs.items():
                try:
                    await self._connect_server(
                        server_config.url,
                        headers=server_config.headers,
                    )
                    logger.info(f"Connected to configured server: {name}")
                except Exception as e:
                    logger.error(f"Failed to connect to {name} ({server_config.url}): {e}")

            self._initialized = True
            logger.info(
                f"Bridge initialized with {len(self._connected_servers)} servers"
            )

    async def _connect_server(
        self,
        server_url: str,
        headers: dict[str, str] | None = None,
    ) -> ConnectedServer:
        """
        Connect to an MCP server with full feature support.

        Args:
            server_url: URL of the MCP server.
            headers: Optional HTTP headers for authentication.

        Returns:
            ConnectedServer instance.
        """
        logger.info(f"Connecting to MCP server: {server_url}")

        # Create transport with optional auth headers
        transport = StreamableHTTPTransport(
            TransportConfig(
                url=server_url,
                timeout=self.config.request_timeout,
                connect_timeout=self.config.connect_timeout,
                headers=headers or {},
            )
        )

        # Create client
        client = MCPClient(
            transport,
            request_timeout=self.config.request_timeout,
        )

        # Connect transport
        await client.connect()

        # Perform capability negotiation
        negotiator = CapabilityNegotiator(
            client,
            client_capabilities=self.config.client_capabilities,
        )
        negotiation = await negotiator.negotiate(timeout=self.config.connect_timeout)

        # Register request handlers for server-initiated features
        utilities = await self._setup_feature_handlers(client, negotiation)

        # Register in server registry
        server_info = ServerInfo(
            url=server_url,
            name=negotiation.server_info.name,
            version=negotiation.server_info.version,
            capabilities=negotiation.server_capabilities.to_dict(),
            connected=True,
            protocol_version=negotiation.protocol_version,
        )
        self._server_registry.register(server_url, server_info)

        # Store connected server with utility handlers
        connected = ConnectedServer(
            url=server_url,
            client=client,
            transport=transport,
            negotiation=negotiation,
            utilities=utilities,
        )
        self._connected_servers[server_url] = connected

        logger.info(f"Connected to {server_info}")
        return connected

    async def _setup_feature_handlers(
        self,
        client: MCPClient,
        negotiation: NegotiationResult,
    ) -> UtilityHandlers:
        """Set up request handlers for server-initiated features."""
        # Sampling handler
        if (
            self.config.enable_sampling
            and negotiation.client_capabilities.supports_sampling()
        ):
            client.on_request(
                "sampling/createMessage",
                self._handle_sampling_request,
            )
            logger.debug("Sampling handler registered")

        # Roots handler
        if negotiation.client_capabilities.supports_roots():
            client.on_request(
                "roots/list",
                self._handle_roots_list,
            )
            logger.debug("Roots handler registered")

        # Elicitation handlers
        if (
            self.config.enable_elicitation
            and negotiation.client_capabilities.supports_elicitation()
        ):
            client.on_request(
                "elicitation/create",
                self._handle_elicitation_request,
            )
            logger.debug("Elicitation handler registered")

        # Set up utility handlers (ping, progress, cancellation, logging)
        utilities = await setup_utility_handlers(
            client,
            negotiation.server_capabilities,
            self.config.logging_config,
        )

        return utilities

    async def _handle_sampling_request(
        self,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Handle sampling/createMessage request from server."""
        # Import here to avoid circular imports
        # These will be implemented in MCP-005
        logger.info(f"Received sampling request: {params}")

        if self._approval_callback:
            approved, modified = await self._approval_callback(
                {"type": "sampling", "params": params}
            )
            if not approved:
                return {"content": {"type": "text", "text": "Sampling request denied"}}
            if modified:
                params = modified

        # TODO: Implement actual sampling via LLM adapter
        return {
            "role": "assistant",
            "content": {"type": "text", "text": "Sampling response placeholder"},
            "model": "unknown",
        }

    async def _handle_roots_list(
        self,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Handle roots/list request from server."""
        # TODO: Implement via RootsManager (MCP-004)
        return {"roots": []}

    async def _handle_elicitation_request(
        self,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Handle elicitation/create request from server."""
        logger.info(f"Received elicitation request: {params}")

        if self._approval_callback:
            approved, result = await self._approval_callback(
                {"type": "elicitation", "params": params}
            )
            if not approved:
                return {"action": "cancel"}
            if result:
                return {"action": "submit", "content": result}

        return {"action": "cancel"}

    async def disconnect_server(self, server_url: str) -> None:
        """
        Disconnect from an MCP server.

        Args:
            server_url: URL of the server to disconnect.
        """
        connected = self._connected_servers.pop(server_url, None)
        if connected:
            logger.info(f"Disconnecting from {server_url}")
            try:
                await connected.client.close()
            except Exception as e:
                logger.error(f"Error closing client: {e}")

            self._server_registry.mark_disconnected(server_url)

    async def shutdown(self) -> None:
        """Shutdown all connections and cleanup."""
        async with self._lock:
            if self._shutting_down:
                return

            self._shutting_down = True
            logger.info("Shutting down hybrid MCP bridge")

            # Disconnect all servers
            for url in list(self._connected_servers.keys()):
                await self.disconnect_server(url)

            self._server_registry.clear()
            self._initialized = False
            self._shutting_down = False

    def get_client(self, server_url: str) -> MCPClient | None:
        """
        Get MCP client for a specific server.

        Args:
            server_url: Server URL.

        Returns:
            MCPClient or None if not connected.
        """
        connected = self._connected_servers.get(server_url)
        return connected.client if connected else None

    def get_connected_servers(self) -> list[str]:
        """Get list of connected server URLs."""
        return list(self._connected_servers.keys())

    def get_utilities(self, server_url: str) -> UtilityHandlers | None:
        """
        Get utility handlers for a specific server.

        Args:
            server_url: Server URL.

        Returns:
            UtilityHandlers or None if not connected.
        """
        connected = self._connected_servers.get(server_url)
        return connected.utilities if connected else None

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """
        List tools from all connected servers in raw MCP format.

        Returns:
            Combined list of tools from all servers (MCP format).
        """
        all_tools: list[dict[str, Any]] = []

        for connected in self._connected_servers.values():
            caps = connected.negotiation.server_capabilities
            if caps.supports_tools():
                try:
                    response = await connected.client.request("tools/list")
                    tools = response.get("tools", [])
                    # Add server URL to each tool for tracking
                    for tool in tools:
                        tool["_server_url"] = connected.url
                    all_tools.extend(tools)
                except Exception as e:
                    logger.error(f"Failed to list tools from {connected.url}: {e}")

        return all_tools

    async def list_tools_openai_format(self) -> list[dict[str, Any]]:
        """
        List tools from all connected servers in OpenAI/Anthropic function calling format.

        Returns:
            Combined list of tools converted to OpenAI format.
        """
        mcp_tools = await self.list_all_tools()
        return [mcp_tool_to_openai(t) for t in mcp_tools]

    async def create_tool_callables(self) -> list[Any]:
        """
        Create callable Python functions for all MCP tools.

        Returns a list of async functions that can be passed to the Dedalus SDK.
        Each function, when called, routes to the appropriate MCP server.
        """
        import inspect

        # Map JSON schema types to Python types
        type_map: dict[str, type] = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        mcp_tools = await self.list_all_tools()
        callables = []

        for tool in mcp_tools:
            tool_name = tool["name"]
            server_url = tool.get("_server_url", "")
            description = tool.get("description", "")
            input_schema = tool.get("inputSchema", {})
            properties = input_schema.get("properties", {})
            required = set(input_schema.get("required", []))

            # Build typed signature from inputSchema
            sig_params = []
            for param_name, param_schema in properties.items():
                json_type = param_schema.get("type", "string")
                py_type = type_map.get(json_type, str)

                if param_name in required:
                    param = inspect.Parameter(
                        param_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=py_type,
                    )
                else:
                    default = param_schema.get("default")
                    param = inspect.Parameter(
                        param_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        default=default,
                        annotation=py_type,
                    )
                sig_params.append(param)

            signature = inspect.Signature(sig_params, return_annotation=str)

            # Create the wrapper function - capture all variables explicitly
            def make_caller(t_name: str, s_url: str, desc: str, sig: inspect.Signature, bridge: "HybridMCPBridge"):
                async def mcp_tool_caller(**kwargs) -> str:
                    """MCP tool caller."""
                    try:
                        result = await bridge.call_tool(s_url, t_name, kwargs)
                        # Extract content from MCP result
                        if isinstance(result, dict):
                            content = result.get("content", [])
                            if isinstance(content, list):
                                texts = []
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        texts.append(item.get("text", ""))
                                return "\n".join(texts) if texts else str(result)
                            return str(content)
                        return str(result)
                    except Exception as e:
                        return f"Error calling {t_name}: {e}"

                # Set function metadata with proper signature
                mcp_tool_caller.__name__ = t_name
                mcp_tool_caller.__doc__ = desc or f"MCP tool: {t_name}"
                mcp_tool_caller.__signature__ = sig

                return mcp_tool_caller

            caller = make_caller(tool_name, server_url, description, signature, self)
            callables.append(caller)

        return callables

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call a tool on a specific server.

        Args:
            server_url: Server URL.
            tool_name: Name of the tool.
            arguments: Tool arguments.

        Returns:
            Tool call result.
        """
        client = self.get_client(server_url)
        if not client:
            raise ValueError(f"Not connected to server: {server_url}")

        return await client.request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )

    async def __aenter__(self) -> "HybridMCPBridge":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.shutdown()
