"""Live progress dashboard — second screen of the TUI."""

from pathlib import Path
from typing import Callable, Optional

from textual import work
from textual.app import ComposeResult
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ProgressBar, RichLog

from mac_cleanup.tui.runner import CleanupResult, CleanupRunner, ModuleResult


class CleanupDone(Message):
    """Posted when the cleanup runner finishes."""

    def __init__(self, result: CleanupResult) -> None:
        super().__init__()
        self.result = result


class ProgressScreen(Screen[None]):
    """Displays live progress while cleanup runs in the background."""

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(
        self,
        enabled_modules: list[str],
        dry_run: bool,
        config_path: Path,
        safe_delete: bool = False,
        update_brew: bool = False,
        module_fns: Optional[dict[str, Callable[..., None]]] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,  # noqa: A002
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._enabled_modules = enabled_modules
        self._dry_run = dry_run
        self._safe_delete = safe_delete
        self._update_brew = update_brew
        self._config_path = config_path
        self._module_fns = module_fns
        self._total = len(enabled_modules)

    def compose(self) -> ComposeResult:
        flags: list[str] = []
        if self._dry_run:
            flags.append("DRY-RUN")
        if self._safe_delete:
            flags.append("SAFE-DELETE")
        if self._update_brew:
            flags.append("BREW-UPDATE")
        mode = ", ".join(flags) if flags else "LIVE"
        yield Header(show_clock=True)
        yield Label(f"Running cleanup ({mode}) — {self._total} modules", id="status-label")
        yield ProgressBar(total=self._total, show_eta=True, id="overall-progress")
        yield RichLog(highlight=True, markup=True, id="log")
        yield Footer()

    def on_mount(self) -> None:
        self._run_cleanup()

    @work(exclusive=True)
    async def _run_cleanup(self) -> None:
        runner = CleanupRunner(config_path=self._config_path, module_fns=self._module_fns)
        log = self.query_one(RichLog)
        bar = self.query_one(ProgressBar)

        def on_start(module_name: str) -> None:
            self.call_from_thread(log.write, f"[cyan]⚙[/cyan]  {module_name}...")

        def on_complete(mod_result: ModuleResult) -> None:
            icon = "[green]✓[/green]" if mod_result.status == "done" else "[red]✗[/red]"
            msg = f"{icon}  {mod_result.name}"
            if mod_result.error:
                msg += f" — [red]{mod_result.error}[/red]"
            self.call_from_thread(log.write, msg)
            self.call_from_thread(bar.advance, 1)

        result = await runner.run(
            enabled_modules=self._enabled_modules,
            dry_run=self._dry_run,
            on_start=on_start,
            on_complete=on_complete,
        )
        self.post_message(CleanupDone(result=result))

    def action_quit(self) -> None:
        self.app.exit()
