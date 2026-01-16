"""Shared types for MCP features."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote


@dataclass
class Root:
    """
    A filesystem root declared to MCP servers.

    Roots inform servers about filesystem boundaries the client
    can operate within, enabling context-aware tool behavior.
    """

    uri: str
    """File URI (file:///path/to/directory)."""

    name: str | None = None
    """Optional human-readable name for the root."""

    @classmethod
    def from_path(cls, path: Path, name: str | None = None) -> "Root":
        """
        Create root from filesystem path.

        Args:
            path: Filesystem path (will be resolved to absolute).
            name: Optional name (defaults to directory name).

        Returns:
            Root instance.

        Raises:
            ValueError: If path does not exist.
        """
        resolved = path.resolve()
        if not resolved.exists():
            raise ValueError(f"Root path does not exist: {resolved}")
        uri = resolved.as_uri()
        return cls(uri=uri, name=name or resolved.name)

    @property
    def path(self) -> Path:
        """
        Extract filesystem path from URI.

        Uses urllib.parse for safe URI handling (SEC-004 fix).

        Returns:
            Path object.

        Raises:
            ValueError: If URI scheme is not file://.
        """
        parsed = urlparse(self.uri)
        if parsed.scheme != "file":
            raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

        # Handle file://localhost/path and file:///path
        path_str = unquote(parsed.path)

        # On Windows, file:///C:/path becomes /C:/path after parsing
        # Remove leading slash if followed by drive letter
        if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
            path_str = path_str[1:]

        return Path(path_str)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to MCP wire format.

        Returns:
            Dict with 'uri' and optionally 'name'.
        """
        result: dict[str, Any] = {"uri": self.uri}
        if self.name:
            result["name"] = self.name
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Root":
        """
        Create from MCP wire format.

        Args:
            data: Dict with 'uri' and optionally 'name'.

        Returns:
            Root instance.
        """
        return cls(
            uri=data["uri"],
            name=data.get("name"),
        )

    def exists(self) -> bool:
        """Check if the root path exists on the filesystem."""
        try:
            return self.path.exists()
        except ValueError:
            return False

    def is_directory(self) -> bool:
        """Check if the root is a directory."""
        try:
            return self.path.is_dir()
        except ValueError:
            return False

    def contains(self, path: Path) -> bool:
        """
        Check if a path is within this root.

        Args:
            path: Path to check.

        Returns:
            True if path is within root.
        """
        try:
            root_path = self.path.resolve()
            check_path = path.resolve()
            return str(check_path).startswith(str(root_path))
        except ValueError:
            return False

    def __str__(self) -> str:
        if self.name:
            return f"Root({self.name}: {self.uri})"
        return f"Root({self.uri})"

    def __repr__(self) -> str:
        return f"Root(uri={self.uri!r}, name={self.name!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Root):
            return False
        return self.uri == other.uri

    def __hash__(self) -> int:
        return hash(self.uri)
