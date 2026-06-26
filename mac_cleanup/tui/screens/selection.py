"""Module selection screen — first screen of the TUI."""

from typing import Optional

from textual.app import ComposeResult
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Header, Label

from mac_cleanup.__version__ import __version__
from mac_cleanup.tui.widgets.module_list import ModuleList


class RunRequested(Message):
    """Posted when user confirms module selection and wants to run cleanup."""

    def __init__(
        self,
        enabled_modules: list[str],
        dry_run: bool,
        safe_delete: bool,
        update_brew: bool,
    ) -> None:
        super().__init__()
        self.enabled_modules = enabled_modules
        self.dry_run = dry_run
        self.safe_delete = safe_delete
        self.update_brew = update_brew


class SelectionScreen(Screen[None]):
    """Scrollable module checklist with keyboard controls."""

    BINDINGS = [
        ("space", "toggle_module", "Toggle"),
        ("a", "select_all", "All"),
        ("n", "deselect_all", "None"),
        ("d", "toggle_dry_run", "Dry-run"),
        ("s", "toggle_safe_delete", "Safe-delete"),
        ("u", "toggle_update", "Brew update"),
        ("r", "run", "Run"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        all_modules: list[str],
        enabled_modules: list[str],
        name: Optional[str] = None,
        id: Optional[str] = None,  # noqa: A002
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._all_modules = all_modules
        self._enabled_modules = enabled_modules
        self.dry_run: bool = False
        self.safe_delete: bool = False
        self.update_brew: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label(self._build_hint_text(), id="hint")
        yield ModuleList()
        yield Footer()

    def _build_hint_text(self) -> str:
        return (
            "[bold]space[/bold] toggle  [bold]a[/bold] all  [bold]n[/bold] none  "
            "[bold]d[/bold] dry-run  [bold]s[/bold] safe-delete  [bold]u[/bold] brew update  "
            "[bold]r[/bold] run  [bold]q[/bold] quit"
        )

    def on_mount(self) -> None:
        ml = self.query_one(ModuleList)
        for sel in ml.build_selections(self._all_modules, self._enabled_modules):
            ml.add_option(sel)
        self._update_header()

    def _update_header(self) -> None:
        flags: list[str] = []
        if self.dry_run:
            flags.append("[yellow]DRY-RUN[/yellow]")
        if self.safe_delete:
            flags.append("[cyan]SAFE-DELETE[/cyan]")
        if self.update_brew:
            flags.append("[magenta]BREW-UPDATE[/magenta]")
        mode = "  ".join(flags) if flags else "[green]LIVE[/green]"
        self.sub_title = f"v{__version__}  |  {mode}"

    def action_toggle_dry_run(self) -> None:
        self.dry_run = not self.dry_run
        self._update_header()

    def action_toggle_safe_delete(self) -> None:
        self.safe_delete = not self.safe_delete
        self._update_header()

    def action_toggle_update(self) -> None:
        self.update_brew = not self.update_brew
        self._update_header()

    def action_select_all(self) -> None:
        self.query_one(ModuleList).select_all()

    def action_deselect_all(self) -> None:
        self.query_one(ModuleList).deselect_all()

    def action_run(self) -> None:
        selected = list(self.query_one(ModuleList).selected)
        if not selected:
            self.notify("Select at least one module.", severity="warning")
            return
        self.post_message(RunRequested(
            enabled_modules=selected,
            dry_run=self.dry_run,
            safe_delete=self.safe_delete,
            update_brew=self.update_brew,
        ))

    def action_quit(self) -> None:
        self.app.exit()
