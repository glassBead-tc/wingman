"""Common UI components for MCP features."""

from __future__ import annotations

from textual.widgets import Static
from textual.widget import Widget
from textual.app import ComposeResult


class LoadingIndicator(Widget):
    """Animated loading indicator with spinner."""

    DEFAULT_CSS = """
    LoadingIndicator {
        height: 3;
        text-align: center;
        color: $primary;
    }
    """

    def __init__(
        self,
        message: str = "Loading...",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize loading indicator.

        Args:
            message: Message to display next to spinner.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.message = message
        self._frame = 0
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._timer = None

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static(f"{self._frames[0]} {self.message}", id="loading-text")

    def on_mount(self) -> None:
        """Start animation when mounted."""
        self._timer = self.set_interval(0.1, self._animate)

    def on_unmount(self) -> None:
        """Stop animation when unmounted."""
        if self._timer:
            self._timer.stop()

    def _animate(self) -> None:
        """Animate the spinner."""
        self._frame = (self._frame + 1) % len(self._frames)
        try:
            text = self.query_one("#loading-text", Static)
            text.update(f"{self._frames[self._frame]} {self.message}")
        except Exception:
            pass  # Widget may have been removed

    def update_message(self, message: str) -> None:
        """Update the loading message."""
        self.message = message


class ErrorDisplay(Widget):
    """Display an error message with styling."""

    DEFAULT_CSS = """
    ErrorDisplay {
        background: $error 20%;
        border: solid $error;
        padding: 1;
        margin: 1 0;
    }

    ErrorDisplay .error-title {
        text-style: bold;
        color: $error;
    }

    ErrorDisplay .error-message {
        margin-top: 1;
    }

    ErrorDisplay .error-code {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        code: int | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize error display.

        Args:
            title: Error title.
            message: Error message.
            code: Optional error code.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.title = title
        self.error_message = message
        self.code = code

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static(f"❌ {self.title}", classes="error-title")
        yield Static(self.error_message, classes="error-message")
        if self.code is not None:
            yield Static(f"Error code: {self.code}", classes="error-code")


class InfoDisplay(Widget):
    """Display an informational message with styling."""

    DEFAULT_CSS = """
    InfoDisplay {
        background: $primary 20%;
        border: solid $primary;
        padding: 1;
        margin: 1 0;
    }

    InfoDisplay .info-title {
        text-style: bold;
        color: $primary;
    }

    InfoDisplay .info-message {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize info display.

        Args:
            title: Info title.
            message: Info message.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.title = title
        self.info_message = message

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static(f"ℹ️ {self.title}", classes="info-title")
        yield Static(self.info_message, classes="info-message")


class SuccessDisplay(Widget):
    """Display a success message with styling."""

    DEFAULT_CSS = """
    SuccessDisplay {
        background: $success 20%;
        border: solid $success;
        padding: 1;
        margin: 1 0;
    }

    SuccessDisplay .success-title {
        text-style: bold;
        color: $success;
    }

    SuccessDisplay .success-message {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize success display.

        Args:
            title: Success title.
            message: Success message.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.title = title
        self.success_message = message

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static(f"✅ {self.title}", classes="success-title")
        yield Static(self.success_message, classes="success-message")


class WarningDisplay(Widget):
    """Display a warning message with styling."""

    DEFAULT_CSS = """
    WarningDisplay {
        background: $warning 20%;
        border: solid $warning;
        padding: 1;
        margin: 1 0;
    }

    WarningDisplay .warning-title {
        text-style: bold;
        color: $warning;
    }

    WarningDisplay .warning-message {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize warning display.

        Args:
            title: Warning title.
            message: Warning message.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.title = title
        self.warning_message = message

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Static(f"⚠️ {self.title}", classes="warning-title")
        yield Static(self.warning_message, classes="warning-message")
