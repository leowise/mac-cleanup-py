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
        """Launch cleanup with enhanced progress reporting and user feedback."""

        from mac_cleanup.progress import ProgressBar

        # Free space before the run
        free_space_before = self.count_free_space()

        # Track total items processed and bytes cleaned
        total_processed = 0
        total_cleaned_bytes = 0

        for unit in self.base_collector._execute_list:  # noqa
            unit_name = unit.message.replace("Cleaning ", "").replace("...", "")
            console.print(f"[info]🔍 Scanning {unit_name}...[/info]")

            # Process each module with enhanced progress reporting
            for module in ProgressBar.wrap_iter(
                unit.modules,
                description=f"Cleaning {unit_name}",
                total=len(unit.modules),
                status="Processing..."
            ):
                try:
                    # Execute module
                    result = module._execute()  # noqa
                    total_processed += 1

                    # Track successful operations (if module returns size info)
                    if hasattr(module, "get_path") and hasattr(module, "get_command"):
                        # This is a path cleanup module
                        from pathlib import Path
                        path = Path(module.get_path)
                        if not path.exists():
                            # Assume successful deletion, estimate size if possible
                            total_cleaned_bytes += getattr(result, "size", 0)

                except Exception as e:
                    # Log but continue with other modules
                    from mac_cleanup.logger import logger
                    logger.log_operation(str(module), 0, "module_error", False)
                    console.print(f"[warning]⚠️  Skipped {unit_name} module due to error: {e}[/warning]")
                    continue

        # Free space after the run
        free_space_after = self.count_free_space()
        actual_cleaned = free_space_after - free_space_before

        # Enhanced results display
        if actual_cleaned > 0:
            print_panel(
                text=f"[success]✅ Cleanup Complete![/success]\n\n"
                     f"[info]📊 Summary:[/info]\n"
                     f"• Processed: [bold]{total_processed}[/bold] cleanup operations\n"
                     f"• Space recovered: [success]{bytes_to_human(actual_cleaned)}[/success]\n"
                     f"• Free space now: [info]{bytes_to_human(free_space_after)}[/info]",
                title="[success]Success"
            )
        else:
            print_panel(
                text="[info]🧹 Cleanup completed with no space recovered.[/info]\n\n"
                     "This could mean:\n"
                     "• Files were already clean\n"
                     "• Some operations were skipped for safety\n"
                     "• Check the logs for any issues",
                title="[info]No Changes"
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

            console.print("[info]🔍 Performing dry run analysis...[/info]")

            estimate_size: float = 0
            blocked_paths = 0

            for path, size in self.base_collector._extract_paths():
                if args.verbose and size:
                    # Show security status for each path
                    from mac_cleanup.utils import check_deletable
                    is_safe = check_deletable(path)

                    status_icon = "✅" if is_safe else "❌"
                    status_color = "success" if is_safe else "danger"

                    if not is_safe:
                        blocked_paths += 1

                    console.print(
                        f"[{status_color}]{status_icon}[/{status_color}] "
                        f"{bytes_to_human(size)} - {path}",
                        no_wrap=True
                    )
                estimate_size += size

            freed_space = bytes_to_human(estimate_size)

            # Show security summary
            security_status = "success" if blocked_paths == 0 else "warning"
            security_icon = "🛡️" if blocked_paths == 0 else "⚠️"

            print_panel(
                text=f"[info]📊 Dry Run Results:[/info]\n\n"
                     f"Estimated space to recover: [success]{freed_space}[/success]\n"
                     f"Total items analyzed: [info]{len(list(self.base_collector._extract_paths()))}[/info]\n\n"
                     f"[{security_status}]{security_icon} Security Status:[/{security_status}]\n"
                     f"• Safe operations: [success]{len(list(self.base_collector._extract_paths())) - blocked_paths}[/success]\n"
                     f"• Blocked for safety: [warning]{blocked_paths}[/warning]",
                title="[info]Dry Run Complete"
            )

            try:
                continue_cleanup = Confirm.ask(
                    "\n🚀 Proceed with actual cleanup?",
                    show_default=False,
                    default="y"
                )
            # Cyrillic symbols may crash rich.Confirm
            except UnicodeDecodeError:
                console.clear()
                console.print("Do not enter symbols that can't be decoded to UTF-8", style="danger")
                console.print("Exiting...")
                return

            console.clear()

            # Exit if user doesn't want to continue
            if not continue_cleanup:
                console.print("[info]🛑 Cleanup cancelled by user.[/info]")
                return

        # Clean stuff up
        self.cleanup()


if __name__ == "__main__":
    EntryPoint().start()  # pragma: no cover (coverage marks line as untested)
