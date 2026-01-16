"""Transport layer types and configuration."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class TransportEventType(Enum):
    """Types of transport events for observability."""

    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    DISCONNECTED = auto()
    MESSAGE_SENT = auto()
    MESSAGE_RECEIVED = auto()
    ERROR = auto()
    SESSION_ESTABLISHED = auto()
    SSE_OPENED = auto()
    SSE_CLOSED = auto()


@dataclass
class TransportEvent:
    """Event emitted by transport for observability."""

    type: TransportEventType
    timestamp: float
    data: dict[str, Any] | None = None
    error: Exception | None = None

    def __str__(self) -> str:
        base = f"[{self.type.name}]"
        if self.data:
            base += f" {self.data}"
        if self.error:
            base += f" error={self.error}"
        return base


@dataclass
class TransportConfig:
    """Configuration for MCP transport layer."""

    url: str
    """Base URL of the MCP server (must be https:// for remote servers)."""

    timeout: float = 30.0
    """Request timeout in seconds."""

    connect_timeout: float = 10.0
    """Connection establishment timeout in seconds."""

    headers: dict[str, str] = field(default_factory=dict)
    """Additional HTTP headers to include in requests."""

    keep_alive: bool = True
    """Whether to use HTTP keep-alive for connection reuse."""

    max_concurrent_requests: int = 10
    """Maximum number of concurrent in-flight requests."""

    verify_ssl: bool = True
    """Whether to verify SSL certificates (always True for production)."""

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.url:
            raise ValueError("url is required")
        # Allow http:// only for localhost development
        if self.url.startswith("http://") and not self._is_localhost():
            raise ValueError("Remote connections must use https://")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        if self.max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests must be at least 1")

    def _is_localhost(self) -> bool:
        """Check if URL points to localhost."""
        from urllib.parse import urlparse

        parsed = urlparse(self.url)
        host = parsed.hostname or ""
        return host in ("localhost", "127.0.0.1", "::1", "[::1]")
