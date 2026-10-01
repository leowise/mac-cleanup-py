"""Application-specific exceptions and recovery guidance."""

from typing import Optional


class MacCleanupError(Exception):
    """Base class for recoverable mac-cleanup failures."""

    user_message = "The cleanup operation could not be completed."
    recovery_hint = "Try a dry run first, then retry the operation."

    def __init__(self, message: str = "", *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message or self.user_message)
        self.cause = cause

    @property
    def recovery_message(self) -> str:
        """Return concise guidance suitable for user-facing output."""
        return f"{self.user_message} {self.recovery_hint}"


class CommandError(MacCleanupError, RuntimeError):
    """A permitted command failed to execute successfully."""

    user_message = "A cleanup command failed."
    recovery_hint = "Check the command and system permissions, then retry."


class CommandTimeoutError(CommandError, TimeoutError):
    """A command exceeded its safety timeout."""

    user_message = "A cleanup command timed out."
    recovery_hint = "Retry with fewer items or smaller batches."


class CommandValidationError(MacCleanupError, ValueError):
    """A command was rejected before execution."""

    user_message = "A command was blocked for safety."
    recovery_hint = "Review the selected cleanup module and use a supported command."


class OperationError(MacCleanupError):
    """A cleanup operation failed after it started."""

    user_message = "The cleanup operation was not completed."
    recovery_hint = "Use the backup restore option if files need to be recovered."
