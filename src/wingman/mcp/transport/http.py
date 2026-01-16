"""Streamable HTTP transport implementation for MCP."""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Any

import httpx

from wingman.lib import oj
from wingman.mcp.transport.base import (
    Transport,
    TransportError,
    ConnectionError,
    TimeoutError,
    SessionError,
)
from wingman.mcp.transport.types import (
    TransportConfig,
    TransportEvent,
    TransportEventType,
)


class StreamableHTTPTransport(Transport):
    """
    Streamable HTTP transport per MCP 2025-11-25 specification.

    This transport supports:
    - HTTP POST for client-to-server messages
    - Server-Sent Events (SSE) for server-to-client streaming
    - Session management via Mcp-Session-Id header
    - Concurrent request handling
    """

    MCP_SESSION_HEADER = "Mcp-Session-Id"

    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None
        self._connected: bool = False
        self._response_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._sse_task: asyncio.Task | None = None
        self._sse_response: httpx.Response | None = None
        self._pending_requests: dict[str | int, asyncio.Future] = {}
        self._request_semaphore: asyncio.Semaphore | None = None
        self._closing: bool = False

    async def connect(self) -> None:
        """
        Initialize HTTP client and prepare for communication.

        The actual MCP session is established on first message exchange,
        not during connect().
        """
        if self._connected:
            return

        self._emit_event(
            TransportEvent(
                type=TransportEventType.CONNECTING,
                timestamp=time.time(),
                data={"url": self.config.url},
            )
        )

        try:
            timeout = httpx.Timeout(
                connect=self.config.connect_timeout,
                read=self.config.timeout,
                write=self.config.timeout,
                pool=self.config.timeout,
            )

            # Don't use base_url as httpx adds trailing slashes which break some servers
            # Disable HTTP/2 as some MCP servers have compatibility issues
            self._client = httpx.AsyncClient(
                timeout=timeout,
                headers=self.config.headers,
                verify=self.config.verify_ssl,
                http2=False,
            )

            self._request_semaphore = asyncio.Semaphore(
                self.config.max_concurrent_requests
            )
            self._connected = True
            self._closing = False

            self._emit_event(
                TransportEvent(
                    type=TransportEventType.CONNECTED,
                    timestamp=time.time(),
                )
            )

        except Exception as e:
            raise ConnectionError(f"Failed to initialize HTTP client: {e}", cause=e)

    async def disconnect(self) -> None:
        """Close all connections and cleanup resources."""
        if not self._connected and self._client is None:
            return

        self._closing = True

        self._emit_event(
            TransportEvent(
                type=TransportEventType.DISCONNECTING,
                timestamp=time.time(),
            )
        )

        # Cancel SSE task if running
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
            self._sse_task = None

        # Close SSE response if open
        if self._sse_response:
            await self._sse_response.aclose()
            self._sse_response = None

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        # Close HTTP client
        if self._client:
            await self._client.aclose()
            self._client = None

        self._connected = False
        self._session_id = None

        self._emit_event(
            TransportEvent(
                type=TransportEventType.DISCONNECTED,
                timestamp=time.time(),
            )
        )

    async def send(self, message: dict) -> dict | None:
        """
        Send a JSON-RPC message via HTTP POST.

        Returns:
            Immediate response if server responds directly, None if SSE-upgraded.
        """
        if not self._client or not self._connected:
            raise SessionError("Transport not connected")

        if self._closing:
            raise SessionError("Transport is closing")

        # Acquire semaphore for concurrent request limiting
        if self._request_semaphore:
            await self._request_semaphore.acquire()

        try:
            return await self._send_internal(message)
        finally:
            if self._request_semaphore:
                self._request_semaphore.release()

    async def _send_internal(self, message: dict) -> dict | None:
        """Internal send implementation."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        if self._session_id:
            headers[self.MCP_SESSION_HEADER] = self._session_id

        body = oj.dumps(message)

        self._emit_event(
            TransportEvent(
                type=TransportEventType.MESSAGE_SENT,
                timestamp=time.time(),
                data={"method": message.get("method"), "id": message.get("id")},
            )
        )

        try:
            # Use full URL to avoid trailing slash issues with base_url
            response = await self._client.post(
                self.config.url,
                content=body,
                headers=headers,
            )
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request timed out: {e}", cause=e)
        except httpx.HTTPError as e:
            raise TransportError(f"HTTP error: {e}", cause=e)

        # Extract session ID from response
        if self.MCP_SESSION_HEADER in response.headers:
            new_session = response.headers[self.MCP_SESSION_HEADER]
            if self._session_id != new_session:
                self._session_id = new_session
                self._emit_event(
                    TransportEvent(
                        type=TransportEventType.SESSION_ESTABLISHED,
                        timestamp=time.time(),
                        data={"session_id": self._session_id},
                    )
                )

        # Handle response based on content type
        content_type = response.headers.get("Content-Type", "")

        if response.status_code == 202:
            # Accepted - no immediate response, results via SSE
            return None

        if "text/event-stream" in content_type:
            # Server upgraded to SSE stream
            await self._start_sse_stream(response)
            return None

        if response.status_code >= 400:
            # HTTP error response
            error_body = response.text
            raise TransportError(
                f"HTTP {response.status_code}: {error_body}"
            )

        # Parse and return immediate JSON response
        if "application/json" in content_type:
            try:
                result = oj.loads(response.content)
                self._emit_event(
                    TransportEvent(
                        type=TransportEventType.MESSAGE_RECEIVED,
                        timestamp=time.time(),
                        data={"id": result.get("id") if isinstance(result, dict) else None},
                    )
                )
                return result
            except Exception as e:
                raise TransportError(f"Failed to parse response: {e}", cause=e)

        return None

    async def _start_sse_stream(self, response: httpx.Response) -> None:
        """Start background task to process SSE stream."""
        if self._sse_task and not self._sse_task.done():
            # Already have an SSE stream, close the old one
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass

        self._sse_response = response
        self._sse_task = asyncio.create_task(self._process_sse_stream(response))

        self._emit_event(
            TransportEvent(
                type=TransportEventType.SSE_OPENED,
                timestamp=time.time(),
            )
        )

    async def _process_sse_stream(self, response: httpx.Response) -> None:
        """Process Server-Sent Events stream in background."""
        try:
            async for message in self._parse_sse_stream(response):
                await self._response_queue.put(message)
                self._emit_event(
                    TransportEvent(
                        type=TransportEventType.MESSAGE_RECEIVED,
                        timestamp=time.time(),
                        data={"id": message.get("id"), "method": message.get("method")},
                    )
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._closing:
                self._emit_event(
                    TransportEvent(
                        type=TransportEventType.ERROR,
                        timestamp=time.time(),
                        error=e,
                    )
                )
        finally:
            self._emit_event(
                TransportEvent(
                    type=TransportEventType.SSE_CLOSED,
                    timestamp=time.time(),
                )
            )

    async def _parse_sse_stream(
        self, response: httpx.Response
    ) -> AsyncIterator[dict]:
        """Parse Server-Sent Events stream into JSON-RPC messages."""
        buffer = ""

        async for chunk in response.aiter_text():
            buffer += chunk

            # Process complete events (delimited by double newlines)
            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                event = self._parse_sse_event(event_str)

                if event and "data" in event:
                    try:
                        yield oj.loads(event["data"])
                    except Exception:
                        # Skip malformed JSON in SSE data
                        pass

    def _parse_sse_event(self, event_str: str) -> dict[str, str] | None:
        """
        Parse a single SSE event into its components.

        SSE format:
            event: <event-type>
            data: <data>
            id: <id>

        We only care about the data field for JSON-RPC messages.
        """
        if not event_str.strip():
            return None

        event: dict[str, str] = {}
        data_lines: list[str] = []

        for line in event_str.split("\n"):
            line = line.strip()
            if not line or line.startswith(":"):
                # Comment or empty line
                continue

            if ":" in line:
                field, _, value = line.partition(":")
                value = value.lstrip()  # Remove leading space after colon

                if field == "data":
                    # Data can span multiple lines
                    data_lines.append(value)
                elif field in ("event", "id", "retry"):
                    event[field] = value

        if data_lines:
            event["data"] = "\n".join(data_lines)

        return event if event else None

    async def receive(self) -> AsyncIterator[dict]:
        """
        Async iterator yielding messages from the server.

        Messages come from:
        - SSE stream (server-initiated)
        - Queued responses from send() calls
        """
        while self._connected and not self._closing:
            try:
                # Wait for next message with timeout to allow periodic checks
                message = await asyncio.wait_for(
                    self._response_queue.get(),
                    timeout=1.0,
                )
                yield message
            except asyncio.TimeoutError:
                # Check connection state and continue
                continue
            except asyncio.CancelledError:
                break

    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self._connected and not self._closing

    @property
    def session_id(self) -> str | None:
        """Current MCP session ID."""
        return self._session_id

    def _enqueue_response(self, response: dict) -> None:
        """
        Enqueue a response for the receive() iterator.

        Called when send() receives an immediate JSON response that
        should also be available via receive().
        """
        self._response_queue.put_nowait(response)

    async def cancel_request(self, request_id: str | int) -> bool:
        """
        Attempt to cancel a pending request.

        Note: This only cancels client-side waiting. The server may
        still process the request.

        Args:
            request_id: The JSON-RPC id of the request to cancel.

        Returns:
            True if request was found and cancelled, False otherwise.
        """
        if request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.cancel()
                return True
        return False
