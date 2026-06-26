"""Main Textual application — owns screen transitions."""

from os import environ
from pathlib import Path
from typing import Callable, Optional

from textual import work
from textual.app import App

from mac_cleanup.tui.screens.loading import LoadingScreen
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
        self._all_modules: dict[str, Callable[..., None]] = {}
        self._enabled_modules: list[str] = []

    def on_mount(self) -> None:
        self.push_screen(LoadingScreen())
        self._probe_and_show_selection()

    @work(thread=True)
    def _probe_and_show_selection(self) -> None:
        """Load config, probe installed apps, then switch to SelectionScreen."""
        from mac_cleanup.tui.probe import probe_available_modules

        self._load_modules()
        available = probe_available_modules(self._all_modules)
        enabled = [m for m in self._enabled_modules if m in available]

        self.call_from_thread(self._show_selection, available, enabled)

    def _show_selection(self, available: list[str], enabled: list[str]) -> None:
        self.pop_screen()
        self.push_screen(SelectionScreen(all_modules=available, enabled_modules=enabled))

    def _load_modules(self) -> None:
        """Load module functions from config; falls back to all default modules on failure."""
        try:
            from mac_cleanup.config import Config
            from mac_cleanup.core import _Collector

            _Collector._shared_instance.clear()
            _Collector()
            config = Config(config_path_=self._config_path)
            self._all_modules = config.get_modules
            self._enabled_modules = list(config.get_config_data.get("enabled", []))
        except Exception:
            from inspect import getmembers, isfunction

            from mac_cleanup import default_modules

            self._all_modules = dict(getmembers(default_modules, isfunction))
            self._enabled_modules = []

    def _save_config(self, enabled_modules: list[str]) -> None:
        """Persist the selected modules to the config file."""
        try:
            from toml import dump

            self._config_path.parent.mkdir(exist_ok=True, parents=True)
            data = {"enabled": enabled_modules}
            custom_path = None
            if self._config_path.exists():
                from toml import load
                try:
                    existing = load(self._config_path)
                    custom_path = existing.get("custom_path")
                except Exception:
                    pass
            if custom_path:
                data["custom_path"] = custom_path
            with open(self._config_path, "w") as f:
                dump(data, f)
        except Exception:
            self.notify("Failed to save config", severity="warning")

    def on_run_requested(self, message: RunRequested) -> None:
        self._save_config(message.enabled_modules)
        self.push_screen(
            ProgressScreen(
                enabled_modules=message.enabled_modules,
                dry_run=message.dry_run,
                safe_delete=message.safe_delete,
                update_brew=message.update_brew,
                config_path=self._config_path,
                module_fns=self._all_modules,
            )
        )

    def on_cleanup_done(self, message: CleanupDone) -> None:
        self.push_screen(ResultsScreen(result=message.result))
