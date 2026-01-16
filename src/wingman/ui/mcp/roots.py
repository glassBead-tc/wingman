"""Roots management UI components for MCP."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Input, DataTable
from textual.widget import Widget
from textual.message import Message

if TYPE_CHECKING:
    from wingman.mcp.features.roots import RootsManager


class RootAddRequest(Message):
    """Message requesting root addition."""

    def __init__(self, path: Path, name: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.name = name


class RootRemoveRequest(Message):
    """Message requesting root removal."""

    def __init__(self, uri: str) -> None:
        super().__init__()
        self.uri = uri


class RootsPanel(Widget):
    """Panel for managing filesystem roots."""

    BINDINGS = [
        ("a", "add_root", "Add Root"),
        ("d", "remove_root", "Remove"),
        ("delete", "remove_root", "Remove"),
    ]

    DEFAULT_CSS = """
    RootsPanel {
        height: 100%;
        border: solid $primary;
    }

    RootsPanel #roots-header {
        dock: top;
        height: 3;
        background: $primary;
        text-align: center;
        padding: 1;
    }

    RootsPanel #roots-table {
        height: 1fr;
    }

    RootsPanel #roots-footer {
        dock: bottom;
        height: 5;
        padding: 1;
    }

    RootsPanel #new-root-input {
        width: 1fr;
    }

    RootsPanel #roots-buttons {
        align: right middle;
    }
    """

    def __init__(
        self,
        manager: "RootsManager",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize roots panel.

        Args:
            manager: RootsManager to display and modify.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.manager = manager

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static("📁 Filesystem Roots", id="roots-header")

        table = DataTable(id="roots-table")
        table.add_columns("Name", "Path", "Status")
        yield table

        with Vertical(id="roots-footer"):
            with Horizontal():
                yield Input(
                    placeholder="Enter path to add...",
                    id="new-root-input",
                )
            with Horizontal(id="roots-buttons"):
                yield Button("Add [a]", variant="success", id="btn-add")
                yield Button("Remove [d]", variant="error", id="btn-remove")

    def on_mount(self) -> None:
        """Refresh table on mount."""
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the roots table."""
        try:
            table = self.query_one("#roots-table", DataTable)
            table.clear()

            for root in self.manager.roots:
                name = root.name or "-"
                path_str = str(root.path)
                status = "✅" if root.exists() else "❌"
                table.add_row(name, path_str, status, key=root.uri)
        except Exception:
            pass

    def action_add_root(self) -> None:
        """Add a new root."""
        try:
            input_widget = self.query_one("#new-root-input", Input)
            path_str = input_widget.value.strip()

            if not path_str:
                self.notify("Please enter a path", severity="warning")
                return

            path = Path(path_str).expanduser().resolve()
            if not path.exists():
                self.notify(f"Path does not exist: {path}", severity="error")
                return

            try:
                self.manager.add_root(path)
                input_widget.value = ""
                self._refresh_table()
                self.notify(f"Added root: {path}")
                self.post_message(RootAddRequest(path))
            except ValueError as e:
                self.notify(str(e), severity="error")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_remove_root(self) -> None:
        """Remove the selected root."""
        try:
            table = self.query_one("#roots-table", DataTable)
            if table.cursor_row is not None:
                row_key = table.get_row_at(table.cursor_row)
                if row_key and row_key.key:
                    uri = str(row_key.key)
                    if self.manager.remove_root(uri):
                        self._refresh_table()
                        self.notify("Root removed")
                        self.post_message(RootRemoveRequest(uri))
                    else:
                        self.notify("Failed to remove root", severity="error")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-add":
            self.action_add_root()
        elif event.button.id == "btn-remove":
            self.action_remove_root()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter key in input."""
        if event.input.id == "new-root-input":
            self.action_add_root()


class RootsListWidget(Widget):
    """Simple widget showing roots as a list."""

    DEFAULT_CSS = """
    RootsListWidget {
        height: auto;
        padding: 1;
    }

    RootsListWidget .roots-title {
        text-style: bold;
        margin-bottom: 1;
    }

    RootsListWidget .root-item {
        padding-left: 2;
    }

    RootsListWidget .root-item-valid {
        color: $success;
    }

    RootsListWidget .root-item-invalid {
        color: $error;
    }
    """

    def __init__(
        self,
        manager: "RootsManager",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize roots list widget.

        Args:
            manager: RootsManager to display.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.manager = manager

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static("📁 Roots:", classes="roots-title")

        if not self.manager.roots:
            yield Static("No roots configured", classes="root-item")
        else:
            for root in self.manager.roots:
                status = "✅" if root.exists() else "❌"
                name = root.name or root.path.name
                css_class = "root-item-valid" if root.exists() else "root-item-invalid"
                yield Static(
                    f"{status} {name}: {root.path}",
                    classes=f"root-item {css_class}",
                )

    def refresh_roots(self) -> None:
        """Refresh the roots display."""
        self.refresh()
