"""Elicitation feature implementation for MCP."""

from __future__ import annotations

import asyncio
import logging
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Literal
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ElicitationError(Exception):
    """Base error for elicitation operations."""

    pass


class ElicitationTimeoutError(ElicitationError):
    """Elicitation request timed out."""

    pass


class InvalidURLSchemeError(ElicitationError):
    """URL scheme not allowed for security reasons."""

    pass


@dataclass
class ElicitationRequest:
    """Server request for user input."""

    message: str
    """Prompt message to show user."""

    requested_schema: dict[str, Any] | None = None
    """JSON Schema for form elicitation."""

    url: str | None = None
    """URL to open for URL elicitation."""

    expect_callback: bool = False
    """Whether to wait for OAuth callback."""

    timeout: float | None = None
    """Custom timeout for this request."""

    metadata: dict[str, Any] | None = None
    """Additional metadata from server."""

    @classmethod
    def from_dict(cls, params: dict[str, Any]) -> "ElicitationRequest":
        """Parse from MCP request params."""
        return cls(
            message=params.get("message", ""),
            requested_schema=params.get("requestedSchema"),
            url=params.get("url"),
            expect_callback=params.get("expectCallback", False),
            timeout=params.get("timeout"),
            metadata=params.get("_meta"),
        )

    @property
    def is_form_elicitation(self) -> bool:
        """Check if this is a form elicitation."""
        return self.requested_schema is not None

    @property
    def is_url_elicitation(self) -> bool:
        """Check if this is a URL elicitation."""
        return self.url is not None


@dataclass
class ElicitationResponse:
    """Response to elicitation request."""

    action: Literal["submit", "cancel", "dismiss"]
    """Action taken: submit (with data), cancel (user cancelled), dismiss (timeout/error)."""

    content: dict[str, Any] | None = None
    """Form data if action is submit."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP wire format."""
        result: dict[str, Any] = {"action": self.action}
        if self.content is not None:
            result["content"] = self.content
        return result


# Type for form callback
FormCallback = Callable[[ElicitationRequest], Awaitable[ElicitationResponse]]

# Type for URL confirmation callback
URLConfirmCallback = Callable[[str, str], Awaitable[bool]]


@dataclass
class ElicitationConfig:
    """Configuration for elicitation handler."""

    default_timeout: float = 300.0
    """Default timeout in seconds (5 minutes)."""

    callback_host: str = "127.0.0.1"
    """Host to bind OAuth callback server (SEC-003 fix)."""

    callback_port: int = 0
    """Port for OAuth callbacks (0 = random available port)."""

    allowed_url_schemes: list[str] = field(
        default_factory=lambda: ["https", "http"]
    )
    """Allowed URL schemes for security."""

    require_url_confirmation: bool = True
    """Whether to require user confirmation before opening URLs."""


class ElicitationHandler:
    """
    Handles server-initiated elicitation requests.

    Supports two modes:
    - Form elicitation: Display JSON Schema form, return submitted data
    - URL elicitation: Open URL in browser, optionally wait for OAuth callback
    """

    def __init__(
        self,
        config: ElicitationConfig | None = None,
        form_callback: FormCallback | None = None,
        url_confirm_callback: URLConfirmCallback | None = None,
    ):
        """
        Initialize elicitation handler.

        Args:
            config: Elicitation configuration.
            form_callback: Callback for form elicitation (shows UI, returns response).
            url_confirm_callback: Callback to confirm URL opening (message, url) -> bool.
        """
        self.config = config or ElicitationConfig()
        self._form_callback = form_callback
        self._url_confirm_callback = url_confirm_callback
        self._oauth_server: OAuthCallbackServer | None = None
        self._pending_request: ElicitationRequest | None = None

    @property
    def has_pending_request(self) -> bool:
        """Check if there's a pending elicitation request."""
        return self._pending_request is not None

    def set_form_callback(self, callback: FormCallback) -> None:
        """Set the form callback."""
        self._form_callback = callback

    def set_url_confirm_callback(self, callback: URLConfirmCallback) -> None:
        """Set the URL confirmation callback."""
        self._url_confirm_callback = callback

    async def handle_request(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Handle elicitation/create request from server.

        Args:
            params: Request parameters from MCP.

        Returns:
            Elicitation response for MCP.
        """
        request = ElicitationRequest.from_dict(params)
        self._pending_request = request

        timeout = request.timeout or self.config.default_timeout

        logger.info(
            f"Received elicitation request: "
            f"form={request.is_form_elicitation}, url={request.is_url_elicitation}"
        )

        try:
            if request.is_url_elicitation:
                response = await asyncio.wait_for(
                    self._handle_url_elicitation(request),
                    timeout=timeout,
                )
            elif request.is_form_elicitation:
                response = await asyncio.wait_for(
                    self._handle_form_elicitation(request),
                    timeout=timeout,
                )
            else:
                # Simple confirmation
                response = await asyncio.wait_for(
                    self._handle_simple_elicitation(request),
                    timeout=timeout,
                )

            return response.to_dict()

        except asyncio.TimeoutError:
            logger.warning("Elicitation request timed out")
            return ElicitationResponse(action="dismiss").to_dict()

        except ElicitationError as e:
            logger.error(f"Elicitation error: {e}")
            return ElicitationResponse(action="dismiss").to_dict()

        finally:
            self._pending_request = None

    async def _handle_form_elicitation(
        self, request: ElicitationRequest
    ) -> ElicitationResponse:
        """Handle form-based elicitation."""
        if not self._form_callback:
            logger.warning("No form callback configured")
            return ElicitationResponse(action="dismiss")

        # Validate schema is present
        if not request.requested_schema:
            logger.error("Form elicitation without schema")
            return ElicitationResponse(action="dismiss")

        # Invoke form callback (shows UI)
        response = await self._form_callback(request)
        return response

    async def _handle_url_elicitation(
        self, request: ElicitationRequest
    ) -> ElicitationResponse:
        """Handle URL-based elicitation (OAuth flows, etc.)."""
        url = request.url
        if not url:
            return ElicitationResponse(action="dismiss")

        # Validate URL scheme
        parsed = urlparse(url)
        if parsed.scheme not in self.config.allowed_url_schemes:
            logger.error(f"Blocked URL with scheme: {parsed.scheme}")
            raise InvalidURLSchemeError(
                f"URL scheme '{parsed.scheme}' not allowed. "
                f"Allowed: {self.config.allowed_url_schemes}"
            )

        # Request user confirmation if required
        if self.config.require_url_confirmation:
            if self._url_confirm_callback:
                confirmed = await self._url_confirm_callback(request.message, url)
                if not confirmed:
                    return ElicitationResponse(action="cancel")
            else:
                logger.warning("No URL confirm callback, auto-confirming")

        # Open URL in browser
        logger.info(f"Opening URL: {url}")
        webbrowser.open(url)

        # If expecting OAuth callback, wait for it
        if request.expect_callback:
            callback_data = await self._wait_for_oauth_callback()
            if callback_data:
                return ElicitationResponse(action="submit", content=callback_data)
            else:
                return ElicitationResponse(action="dismiss")

        # No callback expected - just return success
        return ElicitationResponse(action="submit")

    async def _handle_simple_elicitation(
        self, request: ElicitationRequest
    ) -> ElicitationResponse:
        """Handle simple message confirmation."""
        # For simple elicitation, use form callback with empty schema
        if self._form_callback:
            return await self._form_callback(request)

        # Auto-confirm if no callback
        return ElicitationResponse(action="submit")

    async def _wait_for_oauth_callback(self) -> dict[str, Any] | None:
        """Wait for OAuth callback on local server."""
        if not self._oauth_server:
            self._oauth_server = OAuthCallbackServer(
                host=self.config.callback_host,
                port=self.config.callback_port,
            )

        try:
            await self._oauth_server.start()
            callback_data = await self._oauth_server.wait_for_callback()
            return callback_data
        finally:
            await self._oauth_server.stop()

    async def cancel_pending(self) -> None:
        """Cancel any pending elicitation request."""
        if self._oauth_server:
            await self._oauth_server.stop()
        self._pending_request = None


class OAuthCallbackServer:
    """
    Local HTTP server for OAuth callback handling.

    Binds to localhost to receive OAuth redirect callbacks.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        """
        Initialize callback server.

        Args:
            host: Host to bind to (SEC-003: use 127.0.0.1 explicitly).
            port: Port to bind to (0 = random available port).
        """
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._callback_received = asyncio.Event()
        self._callback_data: dict[str, Any] | None = None
        self._actual_port: int | None = None

    @property
    def callback_url(self) -> str | None:
        """Get the callback URL for OAuth redirect."""
        if self._actual_port:
            return f"http://{self.host}:{self._actual_port}/callback"
        return None

    async def start(self) -> None:
        """Start the callback server."""
        self._callback_received.clear()
        self._callback_data = None

        self._server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port,
        )

        # Get actual port if 0 was specified
        sockets = self._server.sockets
        if sockets:
            self._actual_port = sockets[0].getsockname()[1]

        logger.info(f"OAuth callback server started on {self.callback_url}")

    async def stop(self) -> None:
        """Stop the callback server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._actual_port = None
            logger.info("OAuth callback server stopped")

    async def wait_for_callback(self, timeout: float = 300.0) -> dict[str, Any] | None:
        """
        Wait for OAuth callback.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Callback data (query parameters) or None on timeout.
        """
        try:
            await asyncio.wait_for(self._callback_received.wait(), timeout=timeout)
            return self._callback_data
        except asyncio.TimeoutError:
            logger.warning("OAuth callback timed out")
            return None

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming HTTP connection."""
        try:
            # Read HTTP request
            data = await reader.read(4096)
            request = data.decode("utf-8")

            # Parse request line
            lines = request.split("\r\n")
            if lines:
                parts = lines[0].split(" ")
                if len(parts) >= 2:
                    path = parts[1]

                    # Extract query parameters
                    if "?" in path:
                        query_string = path.split("?", 1)[1]
                        self._callback_data = self._parse_query_string(query_string)
                    else:
                        self._callback_data = {}

                    self._callback_received.set()

            # Send response
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                "Connection: close\r\n"
                "\r\n"
                "<html><body>"
                "<h1>Authorization Complete</h1>"
                "<p>You can close this window and return to Wingman.</p>"
                "</body></html>"
            )
            writer.write(response.encode())
            await writer.drain()

        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}")

        finally:
            writer.close()
            await writer.wait_closed()

    def _parse_query_string(self, query_string: str) -> dict[str, str]:
        """Parse query string into dict."""
        params: dict[str, str] = {}
        for pair in query_string.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                # URL decode
                from urllib.parse import unquote
                params[unquote(key)] = unquote(value)
        return params
