"""MCP server coordination and registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ServerInfo:
    """Information about a connected MCP server."""

    url: str
    """Server URL."""

    name: str
    """Server name from initialize response."""

    version: str
    """Server version from initialize response."""

    capabilities: dict[str, Any] = field(default_factory=dict)
    """Server capabilities from initialize response."""

    connected: bool = False
    """Whether server is currently connected."""

    protocol_version: str = ""
    """Negotiated protocol version."""

    def supports(self, feature: str) -> bool:
        """Check if server supports a specific feature."""
        return feature in self.capabilities

    def __str__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"ServerInfo({self.name} v{self.version} @ {self.url} [{status}])"


class ServerRegistry:
    """
    Tracks and coordinates MCP server connections.

    Maintains a registry of known servers and their capabilities,
    allowing features to discover which servers support which operations.
    """

    def __init__(self):
        self._servers: dict[str, ServerInfo] = {}
        self._listeners: list[callable] = []

    def register(self, url: str, info: ServerInfo) -> None:
        """
        Register a server.

        Args:
            url: Server URL (used as key).
            info: Server information.
        """
        old_info = self._servers.get(url)
        self._servers[url] = info

        if old_info is None:
            logger.info(f"Registered new server: {info}")
            self._notify("server_added", url, info)
        else:
            logger.debug(f"Updated server info: {info}")
            self._notify("server_updated", url, info)

    def unregister(self, url: str) -> ServerInfo | None:
        """
        Unregister a server.

        Args:
            url: Server URL.

        Returns:
            Removed server info, or None if not found.
        """
        info = self._servers.pop(url, None)
        if info:
            logger.info(f"Unregistered server: {info}")
            self._notify("server_removed", url, info)
        return info

    def get(self, url: str) -> ServerInfo | None:
        """
        Get server info.

        Args:
            url: Server URL.

        Returns:
            ServerInfo or None if not registered.
        """
        return self._servers.get(url)

    def list_all(self) -> list[ServerInfo]:
        """List all registered servers."""
        return list(self._servers.values())

    def list_connected(self) -> list[ServerInfo]:
        """List all connected servers."""
        return [s for s in self._servers.values() if s.connected]

    def list_disconnected(self) -> list[ServerInfo]:
        """List all disconnected servers."""
        return [s for s in self._servers.values() if not s.connected]

    def list_by_feature(self, feature: str) -> list[ServerInfo]:
        """
        List servers supporting a specific feature.

        Args:
            feature: Feature name ('tools', 'resources', 'prompts', 'tasks').

        Returns:
            List of servers supporting the feature.
        """
        return [
            s for s in self._servers.values()
            if s.connected and s.supports(feature)
        ]

    def supports_feature(self, url: str, feature: str) -> bool:
        """
        Check if a server supports a feature.

        Args:
            url: Server URL.
            feature: Feature name.

        Returns:
            True if server is registered, connected, and supports feature.
        """
        info = self._servers.get(url)
        if not info or not info.connected:
            return False
        return info.supports(feature)

    def mark_connected(self, url: str) -> None:
        """Mark a server as connected."""
        if url in self._servers:
            self._servers[url].connected = True
            self._notify("server_connected", url, self._servers[url])

    def mark_disconnected(self, url: str) -> None:
        """Mark a server as disconnected."""
        if url in self._servers:
            self._servers[url].connected = False
            self._notify("server_disconnected", url, self._servers[url])

    def on_change(self, callback: callable) -> None:
        """
        Register callback for registry changes.

        Args:
            callback: Function(event_type, url, info) called on changes.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: callable) -> None:
        """Remove a previously registered callback."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _notify(self, event: str, url: str, info: ServerInfo) -> None:
        """Notify listeners of a change."""
        for listener in self._listeners:
            try:
                listener(event, url, info)
            except Exception as e:
                logger.exception(f"Error in registry listener: {e}")

    def clear(self) -> None:
        """Clear all registered servers."""
        urls = list(self._servers.keys())
        for url in urls:
            self.unregister(url)

    def __len__(self) -> int:
        """Return number of registered servers."""
        return len(self._servers)

    def __contains__(self, url: str) -> bool:
        """Check if server is registered."""
        return url in self._servers

    def __iter__(self):
        """Iterate over server infos."""
        return iter(self._servers.values())
