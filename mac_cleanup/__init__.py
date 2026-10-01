from mac_cleanup.parser import args  # isort: skip_file
from mac_cleanup.core import ProxyCollector as Collector
from mac_cleanup.core_modules import Command, Path
from mac_cleanup.main import EntryPoint

try:
    from mac_cleanup.__version__ import __version__
except ImportError:  # pragma: no cover
    __version__ = "source"

def main() -> None:
    legacy_cli_requested = any(
        (
            args.dry_run,
            args.update,
            args.configure,
            args.custom_path,
            args.force,
            args.verbose,
            args.safe_delete,
            args.restore,
        )
    )
    if args.command == "ui" or (args.command is None and not legacy_cli_requested):
        from mac_cleanup.tui.app import MacCleanupApp

        MacCleanupApp().run()
    else:
        EntryPoint().start()

__title__ = "mac-cleanup-py"
__all__ = ["Collector", "Path", "Command", "args", "main"]
