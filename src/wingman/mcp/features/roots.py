"""Roots feature implementation for MCP."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from wingman.mcp.features.types import Root

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = logging.getLogger(__name__)


class RootsLockedError(Exception):
    """Roots cannot be modified during active operations."""

    pass


@dataclass
class RootsConfig:
    """Configuration for roots management."""

    auto_detect_workspace: bool = True
    """Whether to auto-detect workspace roots."""

    persist_to_config: bool = True
    """Whether to persist roots to configuration."""

    validate_on_add: bool = True
    """Whether to validate path existence when adding roots."""

    common_project_dirs: list[str] = field(
        default_factory=lambda: ["src", "lib", "tests", "docs"]
    )
    """Common project directories to detect."""


class RootsManager:
    """
    Manages filesystem roots for MCP servers.

    Roots inform servers about filesystem boundaries the client
    can operate within.
    """

    def __init__(
        self,
        config: RootsConfig | None = None,
        on_change: Callable[[], Awaitable[None]] | None = None,
    ):
        """
        Initialize roots manager.

        Args:
            config: Roots configuration.
            on_change: Async callback invoked when roots change.
        """
        self.config = config or RootsConfig()
        self._roots: list[Root] = []
        self._on_change = on_change
        self._locked: bool = False

    @property
    def roots(self) -> list[Root]:
        """Get current roots (read-only copy)."""
        return list(self._roots)

    @property
    def is_locked(self) -> bool:
        """Check if roots are locked."""
        return self._locked

    def add_root(self, path: Path, name: str | None = None) -> Root:
        """
        Add a filesystem root.

        Args:
            path: Path to the root directory.
            name: Optional human-readable name.

        Returns:
            The created Root.

        Raises:
            RootsLockedError: If roots are locked.
            ValueError: If path is invalid or root already exists.
        """
        if self._locked:
            raise RootsLockedError("Cannot modify roots during active operations")

        if self.config.validate_on_add and not path.exists():
            raise ValueError(f"Path does not exist: {path}")

        root = Root.from_path(path, name)

        # Check for duplicates
        if any(r.uri == root.uri for r in self._roots):
            raise ValueError(f"Root already exists: {root.uri}")

        self._roots.append(root)
        logger.info(f"Added root: {root}")
        return root

    def remove_root(self, uri: str) -> bool:
        """
        Remove a root by URI.

        Args:
            uri: URI of the root to remove.

        Returns:
            True if root was found and removed.

        Raises:
            RootsLockedError: If roots are locked.
        """
        if self._locked:
            raise RootsLockedError("Cannot modify roots during active operations")

        for i, root in enumerate(self._roots):
            if root.uri == uri:
                removed = self._roots.pop(i)
                logger.info(f"Removed root: {removed}")
                return True
        return False

    def remove_root_by_path(self, path: Path) -> bool:
        """
        Remove a root by filesystem path.

        Args:
            path: Path of the root to remove.

        Returns:
            True if root was found and removed.
        """
        uri = path.resolve().as_uri()
        return self.remove_root(uri)

    def clear_roots(self) -> None:
        """
        Remove all roots.

        Raises:
            RootsLockedError: If roots are locked.
        """
        if self._locked:
            raise RootsLockedError("Cannot modify roots during active operations")
        count = len(self._roots)
        self._roots.clear()
        logger.info(f"Cleared {count} roots")

    def get_root(self, uri: str) -> Root | None:
        """Get a root by URI."""
        for root in self._roots:
            if root.uri == uri:
                return root
        return None

    def get_root_by_path(self, path: Path) -> Root | None:
        """Get a root by filesystem path."""
        uri = path.resolve().as_uri()
        return self.get_root(uri)

    def contains_path(self, path: Path) -> bool:
        """Check if a path is within any declared root."""
        return any(root.contains(path) for root in self._roots)

    def get_containing_root(self, path: Path) -> Root | None:
        """Get the root that contains a path, if any."""
        for root in self._roots:
            if root.contains(path):
                return root
        return None

    async def notify_change(self) -> None:
        """Notify listeners that roots have changed."""
        if self._on_change:
            try:
                await self._on_change()
            except Exception as e:
                logger.error(f"Error in roots change callback: {e}")

    def lock(self) -> None:
        """Lock roots to prevent modification during operations."""
        self._locked = True
        logger.debug("Roots locked")

    def unlock(self) -> None:
        """Unlock roots to allow modification."""
        self._locked = False
        logger.debug("Roots unlocked")

    def auto_detect(self, workspace: Path | None = None) -> list[Root]:
        """
        Auto-detect roots from workspace directory.

        Args:
            workspace: Workspace root path.

        Returns:
            List of detected and added roots.
        """
        detected: list[Root] = []

        if not workspace or not workspace.exists():
            return detected

        # Add workspace root
        try:
            root = self.add_root(workspace, "Workspace")
            detected.append(root)
        except ValueError as e:
            logger.debug(f"Could not add workspace root: {e}")

        # Check for common project directories
        for dir_name in self.config.common_project_dirs:
            subdir = workspace / dir_name
            if subdir.exists() and subdir.is_dir():
                try:
                    root = self.add_root(subdir, dir_name.capitalize())
                    detected.append(root)
                except ValueError:
                    pass  # Already exists or invalid

        logger.info(f"Auto-detected {len(detected)} roots")
        return detected

    def to_list(self) -> list[dict[str, Any]]:
        """
        Convert roots to MCP wire format.

        Returns:
            List of root dicts for JSON serialization.
        """
        return [root.to_dict() for root in self._roots]

    @classmethod
    def from_config(cls, config_data: dict[str, Any]) -> "RootsManager":
        """
        Load roots from configuration data.

        Args:
            config_data: Dict with 'roots' list.

        Returns:
            RootsManager with loaded roots.
        """
        manager = cls(config=RootsConfig(validate_on_add=False))
        for root_data in config_data.get("roots", []):
            try:
                path = Path(root_data["path"])
                name = root_data.get("name")
                if path.exists():
                    manager.add_root(path, name)
                else:
                    logger.warning(f"Skipping non-existent root: {path}")
            except (KeyError, ValueError) as e:
                logger.warning(f"Invalid root config: {e}")
        return manager

    def to_config(self) -> dict[str, Any]:
        """
        Export roots to configuration format.

        Returns:
            Dict suitable for persistence.
        """
        return {
            "roots": [
                {"path": str(root.path), "name": root.name}
                for root in self._roots
            ]
        }

    def __len__(self) -> int:
        return len(self._roots)

    def __iter__(self):
        return iter(self._roots)

    def __contains__(self, item: Root | str | Path) -> bool:
        if isinstance(item, Root):
            return item in self._roots
        elif isinstance(item, str):
            return any(r.uri == item for r in self._roots)
        elif isinstance(item, Path):
            uri = item.resolve().as_uri()
            return any(r.uri == uri for r in self._roots)
        return False


class RootsHandler:
    """Handles roots-related MCP requests."""

    def __init__(self, manager: RootsManager):
        """
        Initialize handler.

        Args:
            manager: RootsManager to use.
        """
        self.manager = manager

    async def handle_list(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """
        Handle roots/list request from server.

        Args:
            params: Request parameters (currently unused).

        Returns:
            Response with 'roots' list.
        """
        return {"roots": self.manager.to_list()}

    def register_handlers(self, client: "MCPClient") -> None:
        """
        Register roots handlers with MCP client.

        Args:
            client: MCPClient to register handlers on.
        """
        client.on_request("roots/list", self.handle_list)
        logger.debug("Registered roots/list handler")


async def send_roots_changed(client: "MCPClient") -> None:
    """
    Send roots list changed notification to server.

    Args:
        client: MCPClient to send notification on.
    """
    await client.notify("notifications/roots/list_changed")
    logger.debug("Sent roots/list_changed notification")
