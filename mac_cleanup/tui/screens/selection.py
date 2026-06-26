"""Module selection screen — first screen of the TUI."""

from typing import Optional

from textual.app import ComposeResult
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Header, Label

from mac_cleanup.tui.widgets.module_list import ModuleList


class RunRequested(Message):
    """Posted when user confirms module selection and wants to run cleanup."""

    def __init__(self, enabled_modules: list[str], dry_run: bool) -> None:
        super().__init__()
        self.enabled_modules = enabled_modules
        self.dry_run = dry_run


class SelectionScreen(Screen[None]):
    """Scrollable module checklist with keyboard controls."""

    BINDINGS = [
        ("space", "toggle_module", "Toggle"),
        ("a", "select_all", "All"),
        ("n", "deselect_all", "None"),
        ("d", "toggle_dry_run", "Dry-run"),
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label(
            "[bold]space[/bold] toggle  [bold]a[/bold] all  [bold]n[/bold] none  "
            "[bold]d[/bold] dry-run  [bold]r[/bold] run  [bold]q[/bold] quit",
            id="hint",
        )
        widget = ModuleList()
        yield widget
        yield Footer()

    def on_mount(self) -> None:
        ml = self.query_one(ModuleList)
        for sel in ml.build_selections(self._all_modules, self._enabled_modules):
            ml.add_option(sel)
        self._update_header()

    def _update_header(self) -> None:
        mode = "[yellow]DRY-RUN[/yellow]" if self.dry_run else "[green]LIVE[/green]"
        self.sub_title = f"Mode: {mode}"

    def action_toggle_dry_run(self) -> None:
        self.dry_run = not self.dry_run
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
        self.post_message(RunRequested(enabled_modules=selected, dry_run=self.dry_run))

    def action_quit(self) -> None:
        self.app.exit()
