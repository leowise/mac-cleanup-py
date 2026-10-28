"""Logging module for mac_cleanup operations."""

from contextlib import suppress
from datetime import datetime
from pathlib import Path

from mac_cleanup.utils import bytes_to_human, ensure_private_dir, open_private


class OperationLogger:
    """Logger for cleanup operations."""

    def __init__(self):
        # Create log directory if it doesn't exist
        # Use a separate directory for logs to avoid conflict with config
        self._log_dir = Path.home() / ".mac_cleanup_logs"
        with suppress(OSError):
            ensure_private_dir(self._log_dir)

        # Log file path
        self._log_file = self._log_dir / "deletion_log.txt"

    def log_operation(self, path: str, size: float, action: str = "delete", success: bool = True) -> None:
        """
        Log a cleanup operation.

        :param path: Path that was operated on
        :param size: Size of the operation in bytes
        :param action: Type of action (delete, move_to_trash, etc.)
        :param success: Whether the operation was successful
        """
        timestamp = datetime.now().isoformat()
        size_human = bytes_to_human(size)
        status = "SUCCESS" if success else "FAILED"

        log_entry = (
            f"[{timestamp}] {status} - {action.upper()}: {path} "
            f"(Size: {size_human})\n"
        )

        try:
            with open_private(self._log_file, "a") as f:
                f.write(log_entry)
        except (OSError, IOError):
            # If we can't write to the log, we don't want to crash the program
            # Just silently fail for logging errors
            pass

    def get_log_path(self) -> Path:
        """Get the path to the log file."""
        return self._log_file

    def read_recent_logs(self, lines: int = 10) -> str:
        """
        Read the most recent log entries.

        :param lines: Number of lines to read
        :return: Recent log entries as string
        """
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return "".join(recent_lines)
        except (OSError, IOError, FileNotFoundError):
            return "No log entries found."


# Global logger instance
logger = OperationLogger()