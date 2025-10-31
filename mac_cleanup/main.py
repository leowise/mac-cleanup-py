from os import environ, statvfs
from pathlib import Path

from mac_cleanup.config import Config
from mac_cleanup.console import console, print_panel
from mac_cleanup.core import _Collector
from mac_cleanup.error_handling import catch_exception
from mac_cleanup.parser import args
from mac_cleanup.utils import bytes_to_human


class EntryPoint:
    config_path: Path
    base_collector: _Collector

    def __init__(self):
        if (config_home := environ.get("XDG_CONFIG_HOME")) is not None:
            self.config_path = Path(config_home).expanduser().joinpath("mac_cleanup_py").joinpath("config.toml")
        else:
            self.config_path = Path.home().joinpath(".mac_cleanup_py")

        self.base_collector = _Collector()

    @staticmethod
    def count_free_space() -> float:
        """Get current free space."""

        stat = statvfs("/")
        return float(stat.f_bavail * stat.f_frsize)

    def cleanup(self) -> None:
        """Launch cleanup and print results."""

        from mac_cleanup.progress import ProgressBar

        # Free space before the run
        free_space_before = self.count_free_space()

        for unit in self.base_collector._execute_list:  # noqa
            for module in ProgressBar.wrap_iter(unit.modules, description=unit.message, total=len(unit.modules)):
                # Call for module execution
                module._execute()  # noqa

        # Free space after the run
        free_space_after = self.count_free_space()

        # Print results
        print_panel(
            text=f"Removed - [success]{bytes_to_human(free_space_after - free_space_before)}", title="[info]Success"
        )

    def restore_backups(self) -> None:
        """Interactive backup restoration."""
        from mac_cleanup.backup import backup_manager

        # Get available backups
        backups = backup_manager.list_backups()

        if not backups:
            print_panel(text="No backups available for restoration", title="[info]Backup Restore")
            return

        # Display available backups
        console.print("[bold]Available Backups:[/bold]")
        for i, backup in enumerate(backups, 1):
            console.print(
                f"{i}. {backup['path'].name} - {backup['size_human']} - "
                f"Created: {backup['created'].strftime('%Y-%m-%d %H:%M:%S')}"
            )

        # Get user selection
        from rich.prompt import IntPrompt
        try:
            choice = IntPrompt.ask(
                "Select backup to restore (number)",
                choices=[str(i) for i in range(1, len(backups) + 1)]
            )
        except KeyboardInterrupt:
            console.print("Restore cancelled")
            return

        selected_backup = backups[choice - 1]

        # Confirm restoration
        from rich.prompt import Confirm
        try:
            confirm = Confirm.ask(
                f"Restore {selected_backup['path'].name} to current directory?",
                default=False
            )
        except KeyboardInterrupt:
            console.print("Restore cancelled")
            return

        if not confirm:
            console.print("Restore cancelled")
            return

        # Perform restoration
        console.print(f"Restoring {selected_backup['path'].name}...")
        success = backup_manager.restore_backup(selected_backup["path"])

        if success:
            print_panel(
                text=f"Successfully restored {selected_backup['path'].name}",
                title="[success]Restore Complete"
            )
        else:
            print_panel(
                text=f"Failed to restore {selected_backup['path'].name}",
                title="[danger]Restore Failed"
            )

    @catch_exception
    def start(self) -> None:
        """Start mac_cleanup_py by cleaning console, loading config and parsing argument."""

        # Clear console at the start
        console.clear()

        # Get config
        config = Config(config_path_=self.config_path)

        # Sets custom modules' path if user prompted to and exits
        if args.custom_path:
            # Set custom path and exit
            config.set_custom_path()

        # Check config
        config(configuration_prompted=args.configure)

        # Handle restore mode
        if args.restore:
            self.restore_backups()
            return

        # Handle dry runs
        if args.dry_run:
            from rich.prompt import Confirm

            estimate_size: float = 0

            for path, size in self.base_collector._extract_paths():
                if args.verbose and size:
                    console.print(bytes_to_human(size), path, no_wrap=True)
                estimate_size += size

            freed_space = bytes_to_human(estimate_size)  # noqa

            print_panel(text=f"Approx [success]{freed_space}[/success] will be cleaned", title="[info]Dry run results")

            try:
                continue_cleanup = Confirm.ask("Continue?", show_default=False, default="y")
            # Cyrillic symbols may crash rich.Confirm
            except UnicodeDecodeError:
                console.clear()
                console.print("Do not enter symbols that can't be decoded to UTF-8", style="danger")
                console.print("Exiting...")
                return

            console.clear()

            # Exit if user doesn't want to continue
            if not continue_cleanup:
                console.print("Exiting...")
                return

        # Clean stuff up
        self.cleanup()


if __name__ == "__main__":
    EntryPoint().start()  # pragma: no cover (coverage marks line as untested)
