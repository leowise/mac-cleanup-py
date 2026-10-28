"""All core modules."""

from abc import ABC, abstractmethod
from pathlib import Path as Path_
from typing import Final, Optional, TypeVar, final

from beartype import beartype  # pyright: ignore [reportUnknownVariableType]

from mac_cleanup import args
from mac_cleanup.operation import OperationStatus
from mac_cleanup.progress import ProgressBar
from mac_cleanup.utils import check_deletable, check_exists, cmd

T = TypeVar("T")


class BaseModule(ABC):
    """Base abstract module."""

    __prompt: bool = False
    __prompt_message: str = "Do you want to proceed?"

    @beartype
    def with_prompt(self: T, message_: Optional[str] = None) -> T:
        """
        Execute command with user prompt.

        :param message_: Message to be shown on prompt
        :return: Instance of self from
        :class: `BaseModule`
        """

        if args.force:
            return self

        # Can't be solved without typing.Self
        self.__prompt = True  # pyright: ignore [reportAttributeAccessIssue]

        if message_:
            # Can't be solved without typing.Self
            self.__prompt_message = message_  # pyright: ignore [reportAttributeAccessIssue]

        return self

    @abstractmethod
    def _execute(self) -> bool:
        """Base exec with check for prompt :return: True on successful prompt."""

        # Call prompt if needed
        if self.__prompt:
            # Skip on negative prompt
            return ProgressBar.prompt(prompt_text=self.__prompt_message, prompt_title="Module requires attention")

        return True


class _BaseCommand(BaseModule):
    """Base Command with basic command methods."""

    @beartype
    def __init__(self, command_: Optional[str]):
        self.__command: Final[Optional[str]] = command_

    @property
    def get_command(self) -> Optional[str]:
        """Get command specified to the module."""

        return self.__command

    @abstractmethod
    def _execute(self, ignore_errors: bool = True) -> Optional[str]:
        """
        Execute the command specified.

        :param ignore_errors: Ignore errors during execution
        :return: Command execution results based on specified parameters
        """

        # Skip if there is no command
        if not self.__command:
            return

        # Skip on negative prompt
        if not super()._execute():
            return

        # Execute command
        return cmd(command=self.__command, ignore_errors=ignore_errors)


@final
class Command(_BaseCommand):
    """Collector list unit for command execution."""

    __ignore_errors: bool = True

    def with_errors(self) -> "Command":
        """Return errors in exec output :return: :class:`Command`"""

        self.__ignore_errors = False

        return self

    def _execute(self, ignore_errors: Optional[bool] = None) -> Optional[str]:
        """
        Execute the command specified.

        :param ignore_errors: Overrides flag `ignore_errors` in class
        :return: Command execution results based on specified parameters
        """

        return super()._execute(ignore_errors=self.__ignore_errors if ignore_errors is None else ignore_errors)


@final
class Path(_BaseCommand):
    """Collector list unit for cleaning paths."""

    __dry_run_only: bool = False

    @beartype
    def __init__(self, path: str):
        self.__path: Final[Path_] = Path_(path).expanduser()
        self.__operation_status = OperationStatus.PENDING

        tmp_command = self._delete_command(self.__path)

        super().__init__(command_=tmp_command)

    @staticmethod
    def _delete_command(path: Path_) -> str:
        """Command removing ``path``: Finder trash with safe-delete, otherwise rm -rf."""

        if args.safe_delete:
            # Use osascript to move to trash (safer than rm -rf)
            return "osascript -e 'tell application \"Finder\" to delete " f"POSIX file \"{path.as_posix()}\"'"

        # Use rm -rf for permanent deletion
        return f"rm -rf '{path.as_posix()}'"

    @property
    def get_path(self) -> Path_:
        """Get path specified to the module."""

        return self.__path

    @property
    def operation_status(self) -> OperationStatus:
        """Return the latest state of this cleanup operation."""

        return self.__operation_status

    def dry_run_only(self) -> "Path":
        """Set module to only count size in dry runs :return: :class:`Path`"""

        self.__dry_run_only = True

        return self

    @property
    def __action(self) -> str:
        """Action name used in the operation log."""

        return "move_to_trash" if args.safe_delete else "delete"

    @property
    def __is_glob(self) -> bool:
        """Whether the path contains shell-style wildcards."""

        return any(char in self.__path.as_posix() for char in "*?[")

    def __nothing_to_do(self) -> bool:
        """Dry-run-only paths, undeletable or missing paths, and globs without matches."""

        if self.__dry_run_only:
            return True

        if not all([check_deletable(path=self.__path), check_exists(path=self.__path, expand_user=False)]):
            return True

        # A glob that matches nothing has nothing to confirm, back up or delete
        return self.__is_glob and not self.__remaining()

    def __execute_glob(self, ignore_errors: bool) -> Optional[str]:
        """
        Delete every match of a glob path.

        Commands run without a shell, so wildcards are never expanded by ``rm``. The matches
        are expanded here instead and each one is validated before it is removed.
        """

        from glob import glob

        # Respect the module's own prompt (with_prompt) like any other command
        if not BaseModule._execute(self):
            return None

        output = ""
        for match in sorted(glob(self.__path.as_posix())):
            if check_deletable(path=match):
                output += cmd(self._delete_command(Path_(match)), ignore_errors=ignore_errors) or ""

        return output

    def __remaining(self) -> bool:
        """Whether anything the path (or glob) refers to is still on disk."""

        from glob import glob

        text = self.__path.as_posix()
        if any(char in text for char in "*?["):
            return bool(glob(text))

        return self.__path.exists() or self.__path.is_symlink()

    def __rollback(self, backup_path: Optional[Path_]) -> None:
        """Restore the pre-deletion backup when the target was removed by a failed command."""

        from mac_cleanup.backup import backup_manager
        from mac_cleanup.logger import logger

        # Restore is non-destructive and refuses to overwrite leftovers, so it is only
        # attempted when nothing remains. A partially deleted target stays FAILED and
        # the backup is kept for a manual `restore`.
        restored = (
            backup_path is not None
            and not self.__remaining()
            and backup_manager.restore_backup(backup_path, backup_manager.restore_root(self.__path))
        )
        if restored:
            self.__operation_status = OperationStatus.ROLLED_BACK
            logger.log_operation(self.__path.as_posix(), 0, "rollback", True)
            return

        self.__operation_status = OperationStatus.FAILED

    def __confirmed(self, size: float) -> bool:
        """
        Warn about oversized paths and ask for deletion confirmation.

        Paths over the size limit are always called out; ``--force`` accepts the warning
        and ``--no-size-limit`` suppresses it.
        """

        from mac_cleanup.console import console
        from mac_cleanup.logger import logger
        from mac_cleanup.path_validator import path_validator
        from mac_cleanup.utils import bytes_to_human

        limit = path_validator.size_limits["block_threshold"]
        oversized = size > limit and not args.no_size_limit
        size_warning = (
            f"\n[warning]Larger than the {bytes_to_human(limit)} deletion limit "
            f"(use --no-size-limit to skip this warning).[/warning]"
            if oversized
            else ""
        )

        if oversized:
            logger.log_operation(self.__path.as_posix(), size, "size_limit_warning", True)

        if args.force:
            if oversized:
                console.print(f"[warning]{self.__path.as_posix()} is {bytes_to_human(size)}.{size_warning}[/warning]")
            return True

        from mac_cleanup.progress import ProgressBar

        action_text = "move to trash" if args.safe_delete else "permanently delete"
        prompt_text = (
            f"This will {action_text}: {self.__path.as_posix()}\n"
            f"Estimated size: {bytes_to_human(size)}{size_warning}\n\n"
            f"This action {'cannot be undone' if not args.safe_delete else 'can be undone from Trash'}!"
        )
        return ProgressBar.prompt(prompt_text=prompt_text, prompt_title="[danger]⚠️  DELETION CONFIRMATION REQUIRED")

    def _execute(self, ignore_errors: bool = True) -> Optional[str]:
        """Delete specified path and track its operation status."""

        # Completed or rolled-back paths must not prompt or execute a second time.
        # Skipped and failed paths stay retryable.
        if self.__operation_status.terminal:
            return None

        if self.__nothing_to_do():
            self.__operation_status = OperationStatus.SKIPPED
            return

        from mac_cleanup.core import _Collector
        from mac_cleanup.logger import logger

        size = _Collector._get_size(self.__path)

        if not self.__confirmed(size):
            self.__operation_status = OperationStatus.SKIPPED
            return

        # Create backup before deletion (unless safe_delete is used, since trash is recoverable)
        backup_path = None
        if not args.safe_delete:
            from mac_cleanup.backup import backup_manager
            backup_path = backup_manager.create_backup(self.__path)

        if backup_path:
            self.__operation_status = OperationStatus.BACKED_UP
            logger.log_operation(str(backup_path), size, "backup_created", True)

        try:
            result = (
                self.__execute_glob(ignore_errors) if self.__is_glob else super()._execute(ignore_errors=ignore_errors)
            )
        except Exception:
            logger.log_operation(self.__path.as_posix(), size, self.__action, False)
            self.__rollback(backup_path)
            raise

        # The base command returns None when its own prompt was declined: nothing ran,
        # so the backup taken above is unnecessary.
        if result is None:
            if backup_path:
                backup_path.unlink(missing_ok=True)
            self.__operation_status = OperationStatus.SKIPPED
            return None

        logger.log_operation(self.__path.as_posix(), size, self.__action, True)

        # A successful command leaves nothing behind (the target is in Trash for safe-delete).
        if self.__remaining():
            self.__rollback(backup_path)
        else:
            self.__operation_status = OperationStatus.COMPLETED

        return result
