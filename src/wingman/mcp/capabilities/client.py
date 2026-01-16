"""Client capability definitions for MCP negotiation."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SamplingCapability:
    """
    Client supports server-initiated LLM sampling.

    When declared, servers can request the client to generate
    LLM completions on their behalf.
    """

    pass  # No sub-capabilities currently defined in spec


@dataclass
class RootsCapability:
    """
    Client can declare filesystem roots.

    Roots inform the server about filesystem boundaries the client
    is willing to operate within.
    """

    list_changed: bool = True
    """Whether client will notify server when roots change."""


@dataclass
class ElicitationCapability:
    """
    Client supports user input elicitation.

    Enables servers to request structured input from users
    via forms or URL navigation.
    """

    form: bool = True
    """Whether client supports JSON Schema form elicitation."""

    url: bool = True
    """Whether client supports URL navigation elicitation."""


@dataclass
class TasksCapability:
    """
    Client supports task-based execution.

    Tasks allow long-running operations with progress tracking,
    cancellation, and durable state.
    """

    list: bool = True
    """Whether client supports listing active tasks."""

    cancel: bool = True
    """Whether client supports cancelling tasks."""

    requests: dict[str, dict[str, bool]] = field(default_factory=dict)
    """Which request types can be task-augmented (empty by default for compatibility)."""


@dataclass
class ClientCapabilities:
    """
    All client capabilities for MCP negotiation.

    This structure is sent to the server during initialization
    to declare what features this client supports.
    """

    sampling: SamplingCapability | None = None
    """Server-initiated LLM sampling support."""

    roots: RootsCapability | None = None
    """Filesystem roots declaration support."""

    elicitation: ElicitationCapability | None = None
    """User input elicitation support."""

    tasks: TasksCapability | None = None
    """Task-based execution support."""

    experimental: dict[str, Any] | None = None
    """Experimental capabilities (vendor-specific)."""

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to wire format for initialize request.

        Returns:
            Dict suitable for JSON serialization.
        """
        caps: dict[str, Any] = {}

        if self.sampling is not None:
            caps["sampling"] = {}

        if self.roots is not None:
            caps["roots"] = {"listChanged": self.roots.list_changed}

        if self.elicitation is not None:
            elicit: dict[str, Any] = {}
            if self.elicitation.form:
                elicit["form"] = {}
            if self.elicitation.url:
                elicit["url"] = {}
            caps["elicitation"] = elicit

        if self.tasks is not None:
            tasks_dict: dict[str, Any] = {}
            if self.tasks.list:
                tasks_dict["list"] = {}
            if self.tasks.cancel:
                tasks_dict["cancel"] = {}
            if self.tasks.requests:
                tasks_dict["requests"] = self.tasks.requests
            caps["tasks"] = tasks_dict

        if self.experimental is not None:
            caps["experimental"] = self.experimental

        return caps

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientCapabilities":
        """
        Create from wire format.

        Args:
            data: Dict from JSON deserialization.

        Returns:
            ClientCapabilities instance.
        """
        return cls(
            sampling=SamplingCapability() if "sampling" in data else None,
            roots=RootsCapability(
                list_changed=data.get("roots", {}).get("listChanged", True)
            )
            if "roots" in data
            else None,
            elicitation=ElicitationCapability(
                form="form" in data.get("elicitation", {}),
                url="url" in data.get("elicitation", {}),
            )
            if "elicitation" in data
            else None,
            tasks=TasksCapability(
                list="list" in data.get("tasks", {}),
                cancel="cancel" in data.get("tasks", {}),
                requests=data.get("tasks", {}).get("requests", {}),
            )
            if "tasks" in data
            else None,
            experimental=data.get("experimental"),
        )

    def supports_sampling(self) -> bool:
        """Check if sampling is supported."""
        return self.sampling is not None

    def supports_roots(self) -> bool:
        """Check if roots are supported."""
        return self.roots is not None

    def supports_elicitation(self) -> bool:
        """Check if elicitation is supported."""
        return self.elicitation is not None

    def supports_form_elicitation(self) -> bool:
        """Check if form elicitation is supported."""
        return self.elicitation is not None and self.elicitation.form

    def supports_url_elicitation(self) -> bool:
        """Check if URL elicitation is supported."""
        return self.elicitation is not None and self.elicitation.url

    def supports_tasks(self) -> bool:
        """Check if tasks are supported."""
        return self.tasks is not None


# Default capabilities for Wingman - supports all MCP 2025-11-25 features
DEFAULT_CLIENT_CAPABILITIES = ClientCapabilities(
    sampling=SamplingCapability(),
    roots=RootsCapability(list_changed=True),
    elicitation=ElicitationCapability(form=True, url=True),
    tasks=TasksCapability(),
)
