"""Sampling approval UI components for MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Button, Static, Label
from textual.screen import ModalScreen

if TYPE_CHECKING:
    from wingman.mcp.features.sampling import SamplingRequest, SamplingMessage


@dataclass
class SamplingApprovalResult:
    """Result from sampling approval modal."""

    approved: bool
    modified_request: "SamplingRequest | None" = None
    denial_reason: str | None = None


class SamplingApprovalModal(ModalScreen[SamplingApprovalResult]):
    """
    Modal for reviewing and approving sampling requests.

    Displays the sampling request details and allows the user
    to approve, deny, or edit before approval.
    """

    BINDINGS = [
        ("escape", "deny", "Deny"),
        ("enter", "approve", "Approve"),
        ("e", "edit", "Edit"),
    ]

    DEFAULT_CSS = """
    SamplingApprovalModal {
        align: center middle;
    }

    SamplingApprovalModal #sampling-container {
        width: 80%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    SamplingApprovalModal #sampling-header {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
        text-align: center;
        padding: 1;
    }

    SamplingApprovalModal #sampling-content {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }

    SamplingApprovalModal #sampling-footer {
        dock: bottom;
        height: auto;
        padding: 1;
        align: center middle;
    }

    SamplingApprovalModal .message-block {
        margin: 1 0;
        padding: 1;
        border: solid $secondary;
    }

    SamplingApprovalModal .message-role {
        text-style: bold;
        color: $accent;
    }

    SamplingApprovalModal .message-content {
        margin-left: 2;
    }

    SamplingApprovalModal #model-info {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    SamplingApprovalModal .system-prompt-section {
        background: $surface-darken-1;
        padding: 1;
        margin-bottom: 1;
        border: dashed $secondary;
    }

    SamplingApprovalModal .section-label {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        request: "SamplingRequest",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize sampling approval modal.

        Args:
            request: The sampling request to review.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.request = request
        self._edit_mode = False

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="sampling-container"):
            yield Static("🤖 Sampling Request Approval", id="sampling-header")

            with ScrollableContainer(id="sampling-content"):
                # Model info
                model_info = self._get_model_info()
                yield Static(model_info, id="model-info")

                # System prompt if present
                if self.request.system_prompt:
                    with Vertical(classes="system-prompt-section"):
                        yield Label("System Prompt:", classes="section-label")
                        yield Static(self.request.system_prompt, classes="message-content")

                # Messages
                yield Label("Messages:", classes="section-label")
                for msg in self.request.messages:
                    with Vertical(classes="message-block"):
                        role_label = "👤 User" if msg.role == "user" else "🤖 Assistant"
                        yield Static(role_label, classes="message-role")
                        content = self._format_content(msg.content)
                        yield Static(content, classes="message-content")

            with Horizontal(id="sampling-footer"):
                yield Button("Approve [Enter]", variant="success", id="btn-approve")
                yield Button("Edit [E]", variant="primary", id="btn-edit")
                yield Button("Deny [Esc]", variant="error", id="btn-deny")

    def _format_content(self, content) -> str:
        """Format message content for display."""
        from wingman.mcp.features.sampling import TextContent, ImageContent

        if isinstance(content, TextContent):
            return content.text
        elif isinstance(content, ImageContent):
            return f"[Image: {content.mime_type}]"
        return str(content)

    def _get_model_info(self) -> str:
        """Get model preference info."""
        prefs = self.request.model_preferences
        if not prefs:
            return "Model: Default | Max tokens: " + str(self.request.max_tokens)

        parts = []
        if prefs.hints:
            hints = ", ".join(h.get("name", "?") for h in prefs.hints)
            parts.append(f"Hints: {hints}")
        if prefs.intelligence_priority:
            parts.append(f"Intelligence: {prefs.intelligence_priority:.1f}")
        if prefs.speed_priority:
            parts.append(f"Speed: {prefs.speed_priority:.1f}")
        if prefs.cost_priority:
            parts.append(f"Cost: {prefs.cost_priority:.1f}")

        model_str = " | ".join(parts) if parts else "Model: Default"
        return f"{model_str} | Max tokens: {self.request.max_tokens}"

    def action_approve(self) -> None:
        """Approve the sampling request."""
        self.dismiss(
            SamplingApprovalResult(
                approved=True,
                modified_request=self.request if self._edit_mode else None,
            )
        )

    def action_deny(self) -> None:
        """Deny the sampling request."""
        self.dismiss(
            SamplingApprovalResult(
                approved=False,
                denial_reason="User denied request",
            )
        )

    def action_edit(self) -> None:
        """Enter edit mode."""
        self._edit_mode = True
        self.notify("Edit mode enabled - modify content and press Approve")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-approve":
            self.action_approve()
        elif event.button.id == "btn-deny":
            self.action_deny()
        elif event.button.id == "btn-edit":
            self.action_edit()


class SamplingPreviewWidget(Static):
    """Widget for previewing a sampling message."""

    DEFAULT_CSS = """
    SamplingPreviewWidget {
        padding: 1;
        border: solid $secondary;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        message: "SamplingMessage",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize sampling preview widget.

        Args:
            message: The message to preview.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.message = message

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        from wingman.mcp.features.sampling import TextContent, ImageContent

        role_icon = "👤" if self.message.role == "user" else "🤖"
        yield Static(f"{role_icon} {self.message.role.title()}", classes="message-role")

        content = self.message.content
        if isinstance(content, TextContent):
            yield Static(content.text)
        elif isinstance(content, ImageContent):
            yield Static(f"[Image: {content.mime_type}]")
