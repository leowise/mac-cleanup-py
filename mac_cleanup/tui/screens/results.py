"""Results summary screen — third screen of the TUI."""

from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from mac_cleanup.tui.runner import CleanupResult
from mac_cleanup.utils import bytes_to_human


class ResultsScreen(Screen[None]):
    """Displays total space freed and per-module status after cleanup."""

    BINDINGS = [
        ("r", "run_again", "Run again"),
        ("b", "back", "Back"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        result: CleanupResult,
        name: Optional[str] = None,
        id: Optional[str] = None,  # noqa: A002
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._result = result

    def compose(self) -> ComposeResult:
        mode = "DRY-RUN" if self._result.dry_run else "LIVE"
        freed = bytes_to_human(self._result.total_bytes_freed)
        yield Header(show_clock=True)
        yield Label(
            f"[bold green]Cleanup complete ({mode})[/bold green]\n\n"
            f"Total freed: [bold cyan]{freed}[/bold cyan]",
            id="summary",
        )
        yield DataTable(id="module-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Module", "Status", "Error")
        for mod in self._result.module_results:
            status_markup = {
                "done": "[green]✓ done[/green]",
                "error": "[red]✗ error[/red]",
                "skipped": "[yellow]— skipped[/yellow]",
            }.get(mod.status, mod.status)
            table.add_row(mod.name, status_markup, mod.error or "")

    def action_run_again(self) -> None:
        # Pop results + progress, back to selection
        self.app.pop_screen()
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()
