"""Backup module for mac_cleanup operations."""

import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mac_cleanup.logger import logger
from mac_cleanup.utils import bytes_to_human


class BackupManager:
    """Manager for creating and managing backups."""

    def __init__(self):
        # Create backup directory
        self._backup_dir = Path.home() / ".mac_cleanup_backups"
        self._backup_dir.mkdir(exist_ok=True)

    def create_backup(self, path: Path, description: str = "") -> Optional[Path]:
        """
        Create a tar.gz backup of the given path.

        :param path: Path to backup
        :param description: Optional description for the backup
        :return: Path to the created backup file, or None if failed
        """
        if not path.exists():
            return None

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = str(path).replace("/", "_").replace("\\", "_").lstrip("_")
        backup_name = f"{safe_name}_{timestamp}.tar.gz"
        backup_path = self._backup_dir / backup_name

        try:
            # Create tar.gz archive
            with tarfile.open(backup_path, "w:gz") as tar:
                # Add the path to the archive
                # Use relative path in archive to avoid absolute path issues
                tar.add(path, arcname=path.name)

            return backup_path

        except (OSError, IOError):
            # If backup fails, log it but don't crash the main operation
            logger.log_operation(str(path), 0, "backup_failed", False)
            return None

    def get_backup_info(self, backup_path: Path) -> Dict[str, Any]:
        """
        Get information about a backup file.

        :param backup_path: Path to the backup file
        :return: Dictionary with backup information
        """
        try:
            stat = backup_path.stat()
            return {
                "path": backup_path,
                "size": stat.st_size,
                "size_human": bytes_to_human(stat.st_size),
                "created": datetime.fromtimestamp(stat.st_mtime),
                "exists": True
            }
        except (OSError, FileNotFoundError):
            return {"exists": False}

    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all available backups.

        :return: List of backup information dictionaries
        """
        backups: List[Dict[str, Any]] = []
        if self._backup_dir.exists():
            for backup_file in self._backup_dir.glob("*.tar.gz"):
                backups.append(self.get_backup_info(backup_file))

        # Sort by creation time, newest first
        backups.sort(key=lambda x: x.get("created", datetime.min), reverse=True)
        return backups

    def restore_backup(self, backup_path: Path, restore_dir: Optional[Path] = None) -> bool:
        """
        Restore a backup to the specified directory.

        :param backup_path: Path to the backup file
        :param restore_dir: Directory to restore to (defaults to current dir)
        :return: True if successful
        """
        if not backup_path.exists():
            return False

        restore_dir = (restore_dir or Path.cwd()).expanduser().resolve()
        if not restore_dir.is_dir():
            return False

        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                members = tar.getmembers()
                destinations: List[Path] = []
                for member in members:
                    # Backups must never be able to write outside the target
                    # directory or materialize links/devices during restore.
                    destination = (restore_dir / member.name).resolve()
                    try:
                        destination.relative_to(restore_dir)
                    except ValueError:
                        return False
                    if member.issym() or member.islnk() or member.isdev():
                        return False
                    destinations.append(destination)

                # Restore is intentionally non-destructive: callers must choose
                # another directory if any archived item already exists.
                if len(set(destinations)) != len(destinations) or any(
                    destination.exists() for destination in destinations
                ):
                    return False

                for member in members:
                    tar.extract(member, path=restore_dir)
            return True
        except (OSError, IOError, tarfile.TarError):
            return False

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """
        Remove old backups, keeping only the most recent ones.

        :param keep_count: Number of backups to keep
        :return: Number of backups removed
        """
        backups = self.list_backups()
        if len(backups) <= keep_count:
            return 0

        # Remove old backups
        removed_count = 0
        for backup in backups[keep_count:]:
            try:
                backup["path"].unlink()
                removed_count += 1
            except OSError:
                pass  # Ignore errors when cleaning up

        return removed_count

    def get_backup_dir(self) -> Path:
        """Get the backup directory path."""
        return self._backup_dir


# Global backup manager instance
backup_manager = BackupManager()