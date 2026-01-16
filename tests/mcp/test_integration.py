"""Integration tests for MCP client against real servers."""

import pytest

from wingman.mcp.transport.http import StreamableHTTPTransport
from wingman.mcp.transport.types import TransportConfig
from wingman.mcp.protocol.client import MCPClient
from wingman.mcp.capabilities.negotiation import negotiate_capabilities


class TestThoughtboxIntegration:
    """Integration tests against Thoughtbox MCP server."""

    @pytest.mark.asyncio
    async def test_tool_call_mental_models_list(self, thoughtbox_config):
        """
        Test calling mental_models tool with list_models operation.

        This test validates the entire MCP stack:
        - HTTP transport with headers
        - JSON-RPC messaging
        - Capability negotiation (initialize/initialized)
        - Tool invocation and response parsing
        """
        # Build transport config from .mcp.json
        config = TransportConfig(
            url=thoughtbox_config["url"],
            headers=thoughtbox_config.get("headers", {}),
            timeout=30.0,
        )

        transport = StreamableHTTPTransport(config)
        client = MCPClient(transport)

        try:
            # Connect and negotiate capabilities (levels 1-3)
            await client.connect()
            result = await negotiate_capabilities(client)

            # Verify negotiation succeeded
            assert result.protocol_version in ["2025-11-25", "2024-11-05"]
            assert result.server_info.name == "thoughtbox"

            # Call tool (level 4)
            response = await client.request(
                "tools/call",
                {
                    "name": "mental_models",
                    "arguments": {"operation": "list_models"},
                },
            )

            # Verify response structure
            assert "content" in response
            assert isinstance(response["content"], list)
            assert len(response["content"]) > 0

            # Verify we got text content back
            first_content = response["content"][0]
            assert first_content.get("type") == "text"
            assert "text" in first_content

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_tools_list(self, thoughtbox_config):
        """Test listing available tools from Thoughtbox."""
        config = TransportConfig(
            url=thoughtbox_config["url"],
            headers=thoughtbox_config.get("headers", {}),
        )

        transport = StreamableHTTPTransport(config)
        client = MCPClient(transport)

        try:
            await client.connect()
            await negotiate_capabilities(client)

            # List tools
            response = await client.request("tools/list", {})

            # Verify we got tools back
            assert "tools" in response
            tools = response["tools"]
            assert isinstance(tools, list)

            # Thoughtbox should have these tools
            tool_names = [t["name"] for t in tools]
            assert "thoughtbox" in tool_names
            assert "mental_models" in tool_names

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_client_context_manager(self, thoughtbox_config):
        """Test using client as async context manager."""
        config = TransportConfig(
            url=thoughtbox_config["url"],
            headers=thoughtbox_config.get("headers", {}),
        )

        transport = StreamableHTTPTransport(config)
        client = MCPClient(transport)

        async with client:
            await negotiate_capabilities(client)

            # Should be in READY state
            from wingman.mcp.protocol.state import ProtocolState

            assert client.state == ProtocolState.READY

        # After context exit, should be closed
        assert client.state == ProtocolState.CLOSED
