"""Elicitation UI components for MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Button, Static, Input, Checkbox, Select, Label
from textual.screen import ModalScreen


@dataclass
class FormResult:
    """Result from form elicitation."""

    submitted: bool
    data: dict[str, Any] | None = None


class FormElicitationModal(ModalScreen[FormResult]):
    """
    Modal for rendering JSON Schema forms.

    Dynamically generates form fields from JSON Schema and
    collects user input.
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+enter", "submit", "Submit"),
    ]

    DEFAULT_CSS = """
    FormElicitationModal {
        align: center middle;
    }

    FormElicitationModal #form-container {
        width: 70%;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    FormElicitationModal #form-header {
        dock: top;
        height: auto;
        padding: 1;
        background: $primary;
    }

    FormElicitationModal .form-title {
        text-style: bold;
        color: $text;
    }

    FormElicitationModal .form-description {
        color: $text-muted;
    }

    FormElicitationModal #form-content {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }

    FormElicitationModal .form-field {
        margin: 1 0;
    }

    FormElicitationModal .field-label {
        color: $text;
        margin-bottom: 0;
    }

    FormElicitationModal .field-description {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 0;
    }

    FormElicitationModal .required-marker {
        color: $error;
    }

    FormElicitationModal #form-footer {
        dock: bottom;
        height: auto;
        padding: 1;
        align: center middle;
    }
    """

    def __init__(
        self,
        schema: dict[str, Any],
        title: str | None = None,
        description: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize form elicitation modal.

        Args:
            schema: JSON Schema for the form.
            title: Optional title override.
            description: Optional description override.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.schema = schema
        self.title = title or schema.get("title", "Form")
        self.description = description or schema.get("description", "")
        self._field_widgets: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="form-container"):
            # Header
            with Vertical(id="form-header"):
                yield Static(f"📋 {self.title}", classes="form-title")
                if self.description:
                    yield Static(self.description, classes="form-description")

            # Form fields
            with ScrollableContainer(id="form-content"):
                properties = self.schema.get("properties", {})
                required = self.schema.get("required", [])

                for field_name, prop_schema in properties.items():
                    is_required = field_name in required
                    yield from self._compose_field(field_name, prop_schema, is_required)

            # Footer
            with Horizontal(id="form-footer"):
                yield Button("Submit [Ctrl+Enter]", variant="success", id="btn-submit")
                yield Button("Cancel [Esc]", variant="error", id="btn-cancel")

    def _compose_field(
        self,
        name: str,
        schema: dict[str, Any],
        required: bool,
    ) -> ComposeResult:
        """Compose a form field from JSON Schema."""
        with Vertical(classes="form-field"):
            # Label
            label_text = schema.get("title", name)
            if required:
                label_text += " *"
            yield Label(label_text, classes="field-label")

            # Description
            if "description" in schema:
                yield Static(schema["description"], classes="field-description")

            # Field widget
            widget = self._create_field_widget(name, schema)
            if widget:
                self._field_widgets[name] = widget
                yield widget

    def _create_field_widget(self, name: str, schema: dict[str, Any]) -> Any:
        """Create appropriate widget for schema type."""
        field_type = schema.get("type", "string")

        if field_type == "string":
            if "enum" in schema:
                # Select dropdown
                options = [(v, v) for v in schema["enum"]]
                return Select(options, id=f"field-{name}", allow_blank=True)
            elif schema.get("format") == "password":
                return Input(password=True, id=f"field-{name}")
            else:
                placeholder = str(schema.get("default", ""))
                return Input(placeholder=placeholder, id=f"field-{name}")

        elif field_type == "boolean":
            default = schema.get("default", False)
            return Checkbox(schema.get("title", name), value=default, id=f"field-{name}")

        elif field_type in ("integer", "number"):
            placeholder = str(schema.get("default", ""))
            return Input(placeholder=placeholder, id=f"field-{name}")

        elif field_type == "array":
            # Simple comma-separated input for arrays
            return Input(
                placeholder="Enter comma-separated values", id=f"field-{name}"
            )

        return None

    def _collect_form_data(self) -> dict[str, Any]:
        """Collect data from form widgets."""
        data: dict[str, Any] = {}
        properties = self.schema.get("properties", {})

        for name, widget in self._field_widgets.items():
            prop_schema = properties.get(name, {})
            field_type = prop_schema.get("type", "string")

            if isinstance(widget, Input):
                value = widget.value
                if field_type == "integer":
                    data[name] = int(value) if value else None
                elif field_type == "number":
                    data[name] = float(value) if value else None
                elif field_type == "array":
                    data[name] = [v.strip() for v in value.split(",") if v.strip()]
                else:
                    data[name] = value

            elif isinstance(widget, Checkbox):
                data[name] = widget.value

            elif isinstance(widget, Select):
                data[name] = widget.value if widget.value != Select.BLANK else None

        return data

    def _validate_required(self) -> list[str]:
        """Validate required fields are filled."""
        errors: list[str] = []
        required = self.schema.get("required", [])
        data = self._collect_form_data()

        for field in required:
            value = data.get(field)
            if value is None or value == "" or value == []:
                errors.append(f"'{field}' is required")

        return errors

    def action_submit(self) -> None:
        """Submit the form."""
        errors = self._validate_required()
        if errors:
            self.notify("\n".join(errors), severity="error")
            return

        data = self._collect_form_data()
        self.dismiss(FormResult(submitted=True, data=data))

    def action_cancel(self) -> None:
        """Cancel the form."""
        self.dismiss(FormResult(submitted=False))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-submit":
            self.action_submit()
        elif event.button.id == "btn-cancel":
            self.action_cancel()


class URLElicitationModal(ModalScreen[bool]):
    """
    Modal for URL-based elicitation (OAuth flows).

    Shows the URL to open and waits for the authorization
    callback to complete.
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("o", "open_url", "Open URL"),
    ]

    DEFAULT_CSS = """
    URLElicitationModal {
        align: center middle;
    }

    URLElicitationModal #url-container {
        width: 60%;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    URLElicitationModal .header {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    URLElicitationModal .url-display {
        background: $surface-darken-1;
        padding: 1;
        margin: 1 0;
        border: solid $secondary;
    }

    URLElicitationModal #url-status {
        text-align: center;
        margin: 1 0;
    }

    URLElicitationModal .status-waiting {
        color: $warning;
    }

    URLElicitationModal .status-success {
        color: $success;
    }

    URLElicitationModal .status-error {
        color: $error;
    }

    URLElicitationModal #url-buttons {
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        url: str,
        description: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize URL elicitation modal.

        Args:
            url: URL to open for authorization.
            description: Optional description.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.url = url
        self.description = description
        self._status = "waiting"

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="url-container"):
            yield Static("🔗 External Authorization Required", classes="header")

            if self.description:
                yield Static(self.description)

            yield Static(self.url, classes="url-display")

            yield Static(
                "Waiting for authorization...",
                id="url-status",
                classes="status-waiting",
            )

            with Horizontal(id="url-buttons"):
                yield Button("Open in Browser [O]", variant="primary", id="btn-open")
                yield Button("Cancel [Esc]", variant="error", id="btn-cancel")

    def update_status(self, status: str, message: str) -> None:
        """
        Update the status display.

        Args:
            status: Status type ("waiting", "success", "error").
            message: Status message to display.
        """
        self._status = status
        try:
            status_widget = self.query_one("#url-status", Static)
            status_widget.update(message)
            status_widget.set_class(status == "waiting", "status-waiting")
            status_widget.set_class(status == "success", "status-success")
            status_widget.set_class(status == "error", "status-error")
        except Exception:
            pass

    def action_open_url(self) -> None:
        """Open the URL in browser."""
        import webbrowser

        webbrowser.open(self.url)
        self.notify("Opening URL in browser...")

    def action_cancel(self) -> None:
        """Cancel the authorization."""
        self.dismiss(False)

    def complete_success(self) -> None:
        """Signal successful authorization."""
        self.update_status("success", "Authorization successful!")
        self.dismiss(True)

    def complete_error(self, message: str) -> None:
        """Signal authorization error."""
        self.update_status("error", f"Error: {message}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-open":
            self.action_open_url()
        elif event.button.id == "btn-cancel":
            self.action_cancel()
