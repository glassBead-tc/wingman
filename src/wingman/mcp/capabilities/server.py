"""Server capability definitions for MCP negotiation."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ServerToolsCapability:
    """Server provides tools that can be called by the client."""

    list_changed: bool = False
    """Server will notify when tool list changes."""


@dataclass
class ServerResourcesCapability:
    """Server provides resources that can be read by the client."""

    subscribe: bool = False
    """Client can subscribe to resource changes."""

    list_changed: bool = False
    """Server will notify when resource list changes."""


@dataclass
class ServerPromptsCapability:
    """Server provides prompt templates."""

    list_changed: bool = False
    """Server will notify when prompt list changes."""


@dataclass
class ServerTasksCapability:
    """Server supports task-based execution."""

    list: bool = False
    """Server supports listing active tasks."""

    cancel: bool = False
    """Server supports cancelling tasks."""

    requests: dict[str, dict[str, bool]] | None = None
    """Which request types support task augmentation."""

    def supports_tool_tasks(self) -> bool:
        """Check if server supports task-augmented tool calls."""
        if self.requests is None:
            return False
        tools = self.requests.get("tools", {})
        return bool(tools.get("call"))

    def supports_sampling_tasks(self) -> bool:
        """Check if server supports task-augmented sampling."""
        if self.requests is None:
            return False
        sampling = self.requests.get("sampling", {})
        return bool(sampling.get("createMessage"))

    def supports_elicitation_tasks(self) -> bool:
        """Check if server supports task-augmented elicitation."""
        if self.requests is None:
            return False
        elicitation = self.requests.get("elicitation", {})
        return bool(elicitation.get("create"))


@dataclass
class ServerCapabilities:
    """
    Parsed server capabilities from initialize response.

    Represents what features the connected MCP server supports.
    """

    tools: ServerToolsCapability | None = None
    """Server provides callable tools."""

    resources: ServerResourcesCapability | None = None
    """Server provides readable resources."""

    prompts: ServerPromptsCapability | None = None
    """Server provides prompt templates."""

    tasks: ServerTasksCapability | None = None
    """Server supports task-based execution."""

    logging: bool = False
    """Server supports logging operations."""

    completions: bool = False
    """Server supports argument completion."""

    experimental: dict[str, Any] | None = None
    """Experimental capabilities (vendor-specific)."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerCapabilities":
        """
        Parse from initialize response.

        Args:
            data: The 'capabilities' object from server response.

        Returns:
            ServerCapabilities instance.
        """
        caps = cls()

        if "tools" in data:
            caps.tools = ServerToolsCapability(
                list_changed=data["tools"].get("listChanged", False)
            )

        if "resources" in data:
            caps.resources = ServerResourcesCapability(
                subscribe=data["resources"].get("subscribe", False),
                list_changed=data["resources"].get("listChanged", False),
            )

        if "prompts" in data:
            caps.prompts = ServerPromptsCapability(
                list_changed=data["prompts"].get("listChanged", False)
            )

        if "tasks" in data:
            tasks_data = data["tasks"]
            caps.tasks = ServerTasksCapability(
                list="list" in tasks_data,
                cancel="cancel" in tasks_data,
                requests=tasks_data.get("requests"),
            )

        caps.logging = "logging" in data
        caps.completions = "completions" in data
        caps.experimental = data.get("experimental")

        return caps

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dict for serialization.

        Returns:
            Dict suitable for JSON serialization.
        """
        caps: dict[str, Any] = {}

        if self.tools is not None:
            caps["tools"] = {"listChanged": self.tools.list_changed}

        if self.resources is not None:
            caps["resources"] = {
                "subscribe": self.resources.subscribe,
                "listChanged": self.resources.list_changed,
            }

        if self.prompts is not None:
            caps["prompts"] = {"listChanged": self.prompts.list_changed}

        if self.tasks is not None:
            tasks_dict: dict[str, Any] = {}
            if self.tasks.list:
                tasks_dict["list"] = {}
            if self.tasks.cancel:
                tasks_dict["cancel"] = {}
            if self.tasks.requests:
                tasks_dict["requests"] = self.tasks.requests
            caps["tasks"] = tasks_dict

        if self.logging:
            caps["logging"] = {}

        if self.completions:
            caps["completions"] = {}

        if self.experimental is not None:
            caps["experimental"] = self.experimental

        return caps

    def supports_tools(self) -> bool:
        """Check if server provides tools."""
        return self.tools is not None

    def supports_resources(self) -> bool:
        """Check if server provides resources."""
        return self.resources is not None

    def supports_prompts(self) -> bool:
        """Check if server provides prompts."""
        return self.prompts is not None

    def supports_tasks(self) -> bool:
        """Check if server supports tasks."""
        return self.tasks is not None

    def supports_task_tools(self) -> bool:
        """Check if server supports task-augmented tool calls."""
        return self.tasks is not None and self.tasks.supports_tool_tasks()

    def supports_completions(self) -> bool:
        """Check if server supports argument completion."""
        return self.completions

    def get_available_features(self) -> list[str]:
        """
        List features available with this server.

        Returns:
            List of feature names.
        """
        features = []

        if self.tools is not None:
            features.append("tools")
        if self.resources is not None:
            features.append("resources")
        if self.prompts is not None:
            features.append("prompts")
        if self.tasks is not None:
            features.append("tasks")
        if self.logging:
            features.append("logging")
        if self.completions:
            features.append("completions")

        return features
