"""Backup module for mac_cleanup operations."""

import hashlib
import os
import tarfile
from glob import glob
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mac_cleanup.logger import logger
from mac_cleanup.utils import bytes_to_human


DEFAULT_RETENTION = 10
_GLOB_CHARS = "*?["
_RUN_SEPARATOR = "__"


class BackupManager:
    """Manager for creating and managing backups."""

    def __init__(self):
        # Create backup directory
        self._backup_dir = Path.home() / ".mac_cleanup_backups"
        self._backup_dir.mkdir(exist_ok=True)

        # Backups made by one process share a run id; retention counts runs
        self._run_id = f"run{datetime.now().strftime('%Y%m%d%H%M%S')}{os.getpid()}"
        self._retention = DEFAULT_RETENTION

    @property
    def retention(self) -> int:
        """Number of cleanup runs whose backups are kept (env var overrides the configured value)."""
        try:
            from_env = int(os.environ.get("MAC_CLEANUP_BACKUP_RETENTION", ""))
        except ValueError:
            return self._retention
        return from_env if from_env >= 1 else self._retention

    @retention.setter
    def retention(self, value: int) -> None:
        if value < 1:
            raise ValueError("Backup retention must be at least 1")
        self._retention = value

    @staticmethod
    def restore_root(path: Path) -> Path:
        """
        Directory a backup of ``path`` must be restored into.

        For a glob this is the literal directory before the first wildcard segment, which
        is what the archive members are relative to; otherwise it is the parent directory.
        """
        parts = path.parts
        wildcard_at = next((i for i, part in enumerate(parts) if any(c in part for c in _GLOB_CHARS)), None)
        if wildcard_at is None:
            return path.parent
        return Path(*parts[:wildcard_at]) if wildcard_at else Path("/")

    @classmethod
    def _entries(cls, path: Path) -> List[Tuple[Path, str]]:
        """Existing items to archive for ``path`` (expanding globs) with their archive names."""
        if any(char in path.as_posix() for char in _GLOB_CHARS):
            root = cls.restore_root(path)
            matches = (Path(match) for match in sorted(glob(path.as_posix())))
            return [(match, match.relative_to(root).as_posix()) for match in matches]
        return [(path, path.name)] if path.exists() or path.is_symlink() else []

    def create_backup(self, path: Path, description: str = "") -> Optional[Path]:
        """
        Create a tar.gz backup of the given path (all matches, for a glob).

        :param path: Path to backup
        :param description: Optional description for the backup
        :return: Path to the created backup file, or None if nothing to back up or it failed
        """
        entries = self._entries(path)
        if not entries:
            return None

        # Generate backup filename with timestamp; the digest keeps long paths unique
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join("_" if c in f"/\\{_GLOB_CHARS}]" else c for c in str(path)).lstrip("_")
        digest = hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()[:8]
        backup_name = f"{self._run_id}{_RUN_SEPARATOR}{safe_name[-80:]}_{digest}_{timestamp}.tar.gz"
        backup_path = self._backup_dir / backup_name

        try:
            # Create tar.gz archive with names relative to the restore root
            with tarfile.open(backup_path, "w:gz") as tar:
                for source, arcname in entries:
                    tar.add(source, arcname=arcname)

            self.cleanup_old_backups()
            return backup_path

        except (OSError, tarfile.TarError):
            # Never leave a partial archive that could be mistaken for a complete backup
            backup_path.unlink(missing_ok=True)
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

    @staticmethod
    def _run_key(backup_path: Path) -> str:
        """Group key of a backup: its run id, or its own name for backups from before run ids."""
        run_id, separator, _ = backup_path.name.partition(_RUN_SEPARATOR)
        return run_id if separator else backup_path.name

    def cleanup_old_backups(self, keep_count: Optional[int] = None) -> int:
        """
        Remove the backups of old runs, keeping the most recent ones.

        A run is every backup made by one cleanup process, so a large run is never
        pruned by its own backups. The current run is always kept.

        :param keep_count: Number of runs to keep (defaults to the configured retention)
        :return: Number of backups removed
        """
        keep_count = max(keep_count if keep_count is not None else self.retention, 1)

        # list_backups is newest first, so runs are ordered by their newest backup
        runs: Dict[str, List[Path]] = {}
        for backup in self.list_backups():
            if backup.get("exists"):
                runs.setdefault(self._run_key(backup["path"]), []).append(backup["path"])

        keep = {self._run_id, *list(runs)[:keep_count]}
        removed_count = 0
        for run_key, paths in runs.items():
            if run_key in keep:
                continue
            for path in paths:
                try:
                    path.unlink()
                    removed_count += 1
                except OSError:
                    pass  # Ignore errors when cleaning up

        return removed_count

    def get_backup_dir(self) -> Path:
        """Get the backup directory path."""
        return self._backup_dir


# Global backup manager instance
backup_manager = BackupManager()