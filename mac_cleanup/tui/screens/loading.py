"""Loading screen shown while probing installed apps."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, LoadingIndicator


class LoadingScreen(Screen[None]):
    """Shown briefly while the app probes which modules are applicable."""

    DEFAULT_CSS = """
    LoadingScreen {
        align: center middle;
    }
    #loading-label {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Scanning installed apps…", id="loading-label")
        yield LoadingIndicator()
