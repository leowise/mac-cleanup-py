"""Main Textual application — owns screen transitions."""

from os import environ
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult

from mac_cleanup.tui.screens.progress import CleanupDone, ProgressScreen
from mac_cleanup.tui.screens.results import ResultsScreen
from mac_cleanup.tui.screens.selection import RunRequested, SelectionScreen


def _default_config_path() -> Path:
    if (config_home := environ.get("XDG_CONFIG_HOME")) is not None:
        return Path(config_home).expanduser() / "mac_cleanup_py" / "config.toml"
    return Path.home() / ".mac_cleanup_py"


class MacCleanupApp(App[None]):
    """Interactive TUI for mac-cleanup-py."""

    TITLE = "mac-cleanup"
    SUB_TITLE = "macOS cleanup utility"
    CSS = """
    #hint { color: $text-muted; padding: 0 1; }
    #summary { padding: 1 2; }
    #status-label { padding: 0 1; color: $text-muted; }
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        driver_class: Optional[type] = None,
        css_path: Optional[str] = None,
        watch_css: bool = False,
    ) -> None:
        super().__init__(driver_class=driver_class, css_path=css_path, watch_css=watch_css)
        self._config_path = config_path or _default_config_path()
        self._all_modules: list[str] = []
        self._enabled_modules: list[str] = []

    def on_mount(self) -> None:
        self._load_modules()
        self.push_screen(
            SelectionScreen(
                all_modules=self._all_modules,
                enabled_modules=self._enabled_modules,
            )
        )

    def _load_modules(self) -> None:
        """Load module names from config; falls back to all default modules on failure."""
        try:
            from mac_cleanup.config import Config
            from mac_cleanup.core import _Collector

            _Collector._shared_instance.clear()
            config = Config(config_path_=self._config_path)
            self._all_modules = sorted(config.get_modules.keys())
            self._enabled_modules = list(config.get_config_data.get("enabled", []))
        except Exception:
            from inspect import getmembers, isfunction

            from mac_cleanup import default_modules

            self._all_modules = sorted(name for name, _ in getmembers(default_modules, isfunction))
            self._enabled_modules = []

    def on_run_requested(self, message: RunRequested) -> None:
        self.push_screen(
            ProgressScreen(
                enabled_modules=message.enabled_modules,
                dry_run=message.dry_run,
                config_path=self._config_path,
            )
        )

    def on_cleanup_done(self, message: CleanupDone) -> None:
        self.push_screen(ResultsScreen(result=message.result))
