"""Tests for Streamable HTTP transport."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from wingman.mcp.transport import (
    StreamableHTTPTransport,
    TransportConfig,
    TransportError,
    ConnectionError,
    TimeoutError,
    SessionError,
    TransportEventType,
)


class TestTransportConfig:
    """Tests for TransportConfig validation."""

    def test_valid_https_url(self):
        config = TransportConfig(url="https://example.com/mcp")
        assert config.url == "https://example.com/mcp"

    def test_localhost_http_allowed(self):
        config = TransportConfig(url="http://localhost:8080/mcp")
        assert config.url == "http://localhost:8080/mcp"

    def test_127_0_0_1_http_allowed(self):
        config = TransportConfig(url="http://127.0.0.1:8080/mcp")
        assert config.url == "http://127.0.0.1:8080/mcp"

    def test_remote_http_rejected(self):
        with pytest.raises(ValueError, match="must use https"):
            TransportConfig(url="http://example.com/mcp")

    def test_empty_url_rejected(self):
        with pytest.raises(ValueError, match="url is required"):
            TransportConfig(url="")

    def test_invalid_timeout_rejected(self):
        with pytest.raises(ValueError, match="timeout must be positive"):
            TransportConfig(url="https://example.com", timeout=0)

    def test_invalid_concurrent_requests(self):
        with pytest.raises(ValueError, match="max_concurrent_requests"):
            TransportConfig(url="https://example.com", max_concurrent_requests=0)


class TestStreamableHTTPTransport:
    """Tests for StreamableHTTPTransport."""

    @pytest.fixture
    def config(self):
        return TransportConfig(url="https://example.com/mcp")

    @pytest.fixture
    def transport(self, config):
        return StreamableHTTPTransport(config)

    @pytest.mark.asyncio
    async def test_connect_initializes_client(self, transport):
        """Test that connect() creates HTTP client."""
        await transport.connect()
        assert transport.is_connected()
        assert transport._client is not None
        await transport.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self, transport):
        """Test that disconnect() releases resources."""
        await transport.connect()
        await transport.disconnect()
        assert not transport.is_connected()
        assert transport._client is None

    @pytest.mark.asyncio
    async def test_send_requires_connection(self, transport):
        """Test that send() fails without connection."""
        with pytest.raises(SessionError, match="not connected"):
            await transport.send({"jsonrpc": "2.0", "method": "test", "id": 1})

    @pytest.mark.asyncio
    async def test_context_manager(self, config):
        """Test async context manager protocol."""
        async with StreamableHTTPTransport(config) as transport:
            assert transport.is_connected()
        assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_event_emission(self, transport):
        """Test that transport emits events."""
        events = []
        transport.on_event(lambda e: events.append(e))

        await transport.connect()
        await transport.disconnect()

        event_types = [e.type for e in events]
        assert TransportEventType.CONNECTING in event_types
        assert TransportEventType.CONNECTED in event_types
        assert TransportEventType.DISCONNECTING in event_types
        assert TransportEventType.DISCONNECTED in event_types

    def test_session_id_none_initially(self, transport):
        """Test that session_id is None before first exchange."""
        assert transport.session_id is None


class TestSSEParsing:
    """Tests for SSE event parsing."""

    @pytest.fixture
    def transport(self):
        config = TransportConfig(url="https://example.com")
        return StreamableHTTPTransport(config)

    def test_parse_simple_event(self, transport):
        """Test parsing a simple SSE event."""
        event_str = 'data: {"jsonrpc": "2.0", "result": {}, "id": 1}'
        result = transport._parse_sse_event(event_str)
        assert result is not None
        assert result["data"] == '{"jsonrpc": "2.0", "result": {}, "id": 1}'

    def test_parse_event_with_type(self, transport):
        """Test parsing event with event type."""
        event_str = "event: message\ndata: {}"
        result = transport._parse_sse_event(event_str)
        assert result["event"] == "message"
        assert result["data"] == "{}"

    def test_parse_multiline_data(self, transport):
        """Test parsing multi-line data field."""
        event_str = "data: line1\ndata: line2\ndata: line3"
        result = transport._parse_sse_event(event_str)
        assert result["data"] == "line1\nline2\nline3"

    def test_parse_event_with_id(self, transport):
        """Test parsing event with id field."""
        event_str = "id: 42\ndata: {}"
        result = transport._parse_sse_event(event_str)
        assert result["id"] == "42"

    def test_skip_comments(self, transport):
        """Test that SSE comments are ignored."""
        event_str = ": this is a comment\ndata: {}"
        result = transport._parse_sse_event(event_str)
        assert result["data"] == "{}"
        assert ": this is a comment" not in str(result)

    def test_empty_event_returns_none(self, transport):
        """Test that empty events return None."""
        assert transport._parse_sse_event("") is None
        assert transport._parse_sse_event("   ") is None


class TestConcurrency:
    """Tests for concurrent request handling."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """Test that max_concurrent_requests is enforced."""
        config = TransportConfig(
            url="https://example.com",
            max_concurrent_requests=2,
        )
        transport = StreamableHTTPTransport(config)
        await transport.connect()

        # Verify semaphore was created with correct limit
        assert transport._request_semaphore is not None
        assert transport._request_semaphore._value == 2

        await transport.disconnect()
