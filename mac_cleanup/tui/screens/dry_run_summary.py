"""Dry-run summary screen — shown after analysis, before actual cleanup."""

from typing import Optional

from textual.app import ComposeResult
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from mac_cleanup.tui.runner import CleanupResult
from mac_cleanup.utils import bytes_to_human


class ConfirmCleanup(Message):
    """User confirmed: proceed with actual cleanup."""

    def __init__(self, enabled_modules: list[str]) -> None:
        super().__init__()
        self.enabled_modules = enabled_modules


class DryRunSummaryScreen(Screen[None]):
    """Shows what will be cleaned and estimated space, lets user confirm or cancel."""

    BINDINGS = [
        ("enter", "confirm", "Proceed"),
        ("c", "cancel", "Cancel"),
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
        total_bytes = sum(m.bytes_estimate for m in self._result.module_results)
        modules_with_data = [m for m in self._result.module_results if m.bytes_estimate > 0]
        modules_empty = [m for m in self._result.module_results if m.bytes_estimate == 0 and m.status == "done"]

        yield Header(show_clock=True)
        yield Label(
            f"[bold cyan]Dry-Run Analysis Complete[/bold cyan]\n\n"
            f"Estimated recoverable space: [bold green]{bytes_to_human(total_bytes)}[/bold green]\n"
            f"Modules with data: [bold]{len(modules_with_data)}[/bold]  |  "
            f"Nothing to clean: [dim]{len(modules_empty)}[/dim]\n\n"
            f"[bold]enter[/bold] proceed with cleanup  |  [bold]c[/bold] cancel  |  [bold]q[/bold] quit",
            id="summary",
        )
        yield DataTable(id="module-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Module", "Estimated Size", "Status")

        # Sort by size descending so biggest wins are at top
        sorted_results = sorted(
            self._result.module_results,
            key=lambda m: m.bytes_estimate,
            reverse=True,
        )

        for mod in sorted_results:
            if mod.status == "error":
                size_str = ""
                status = f"[red]✗ {mod.error}[/red]"
            elif mod.bytes_estimate > 0:
                size_str = bytes_to_human(mod.bytes_estimate)
                status = "[green]✓ ready[/green]"
            else:
                size_str = "0B"
                status = "[dim]— nothing to clean[/dim]"
            table.add_row(mod.name, size_str, status)

    def action_confirm(self) -> None:
        modules = [m.name for m in self._result.module_results if m.status == "done" and m.bytes_estimate > 0]
        if not modules:
            self.notify("Nothing to clean up.", severity="warning")
            return
        self.post_message(ConfirmCleanup(enabled_modules=modules))

    def action_cancel(self) -> None:
        # Pop dry-run summary + progress, back to selection
        self.app.pop_screen()
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()
