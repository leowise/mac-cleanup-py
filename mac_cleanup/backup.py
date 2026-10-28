"""Backup module for mac_cleanup operations."""

import hashlib
import os
import shutil
import tarfile
from contextlib import suppress
from datetime import datetime
from glob import glob
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from mac_cleanup.logger import logger
from mac_cleanup.utils import bytes_to_human, ensure_private_dir


DEFAULT_RETENTION = 10
_GLOB_CHARS = "*?["
_RUN_SEPARATOR = "__"
MIN_FREE_AFTER_BACKUP = 100 * 1024 * 1024  # keep this much free after writing a backup


class BackupManager:
    """Manager for creating and managing backups."""

    def __init__(self):
        # Create backup directory
        # Backups can contain tokens and personal data, so only the owner may read them
        self._backup_dir = Path.home() / ".mac_cleanup_backups"
        ensure_private_dir(self._backup_dir)
        for existing in self._backup_dir.glob("*.tar.gz"):
            with suppress(OSError):
                existing.chmod(0o600)

        # Backups made by one process share a run id; retention counts runs
        self._run_id = f"run{datetime.now().strftime('%Y%m%d%H%M%S')}{os.getpid()}"
        self._retention = DEFAULT_RETENTION

        # Archive members skipped by the last restore because they were unsafe
        self.last_skipped: List[str] = []

        # Why the last create_backup failed (None if it succeeded or had nothing to back up)
        self.last_error: Optional[str] = None

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

    @staticmethod
    def _tree_size(entries: List[Tuple[Path, str]]) -> int:
        """Uncompressed size of the items to archive (symlinks are not followed)."""
        total = 0
        for source, _ in entries:
            if source.is_symlink() or source.is_file():
                total += source.lstat().st_size
                continue
            for root, _dirs, files in os.walk(source):
                for name in files:
                    try:
                        total += os.lstat(os.path.join(root, name)).st_size
                    except OSError:
                        continue
        return total

    def create_backup(
        self, path: Path, description: str = "", expected_size: Optional[float] = None
    ) -> Optional[Path]:
        """
        Create a tar.gz backup of the given path (all matches, for a glob).

        Fails without writing anything when the backup directory lacks room for the
        uncompressed data plus ``MIN_FREE_AFTER_BACKUP``; ``last_error`` says why.

        :param path: Path to backup
        :param description: Optional description for the backup
        :param expected_size: Size of the data in bytes if the caller already knows it
        :return: Path to the created backup file, or None if nothing to back up or it failed
        """
        self.last_error = None
        entries = self._entries(path)
        if not entries:
            return None

        needed = (expected_size if expected_size is not None else self._tree_size(entries)) + MIN_FREE_AFTER_BACKUP
        free = shutil.disk_usage(self._backup_dir).free
        if free < needed:
            self.last_error = (
                f"not enough disk space for a backup ({bytes_to_human(needed)} needed, {bytes_to_human(free)} free)"
            )
            logger.log_operation(str(path), 0, "backup_unavailable", False)
            return None

        # Generate backup filename with timestamp; the digest keeps long paths unique
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join("_" if c in f"/\\{_GLOB_CHARS}]" else c for c in str(path)).lstrip("_")
        digest = hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()[:8]
        backup_name = f"{self._run_id}{_RUN_SEPARATOR}{safe_name[-80:]}_{digest}_{timestamp}.tar.gz"
        backup_path = self._backup_dir / backup_name

        try:
            # Create tar.gz archive with names relative to the restore root
            # Created 0600 up front, so the archive is never readable by others, even briefly
            fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
                for source, arcname in entries:
                    tar.add(source, arcname=arcname)

            self.cleanup_old_backups()
            return backup_path

        except (OSError, tarfile.TarError) as err:
            # Never leave a partial archive that could be mistaken for a complete backup
            backup_path.unlink(missing_ok=True)
            self.last_error = f"backup failed: {err}"
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

    @staticmethod
    def _link_is_safe(member: tarfile.TarInfo, restore_dir: Path) -> bool:
        """Whether a symlink member stays inside ``restore_dir`` (hardlinks and devices never do)."""
        if not member.issym() or os.path.isabs(member.linkname):
            return False
        target = os.path.normpath(os.path.join(restore_dir, os.path.dirname(member.name), member.linkname))
        return target == str(restore_dir) or target.startswith(str(restore_dir) + os.sep)

    def _plan_restore(self, members: List[tarfile.TarInfo], restore_dir: Path) -> Optional[List[tarfile.TarInfo]]:
        """
        Decide what to extract; ``None`` means the archive must be refused entirely.

        Members that escape the restore directory, or are written through an archived
        symlink, refuse the whole archive. Unsafe links and special files are skipped
        and reported in ``last_skipped``.
        """
        self.last_skipped = []
        extract: List[tarfile.TarInfo] = []
        symlinks: set[str] = set()
        seen: set[str] = set()

        for member in members:
            destination = Path(os.path.normpath(restore_dir / member.name))
            if destination != restore_dir and restore_dir not in destination.parents:
                return None

            # Never write below a symlink that this archive creates
            if any(str(parent) in symlinks for parent in PurePosixPath(member.name).parents):
                return None

            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                if not self._link_is_safe(member, restore_dir):
                    self.last_skipped.append(member.name)
                    continue
                symlinks.add(member.name)

            # Restore is non-destructive: nothing may already exist (even a dangling symlink)
            resolved_parent = destination.parent.resolve()
            if member.name in seen or os.path.lexists(resolved_parent / destination.name):
                return None
            if restore_dir not in (resolved_parent, *resolved_parent.parents):
                return None

            seen.add(member.name)
            extract.append(member)

        return extract

    def restore_backup(self, backup_path: Path, restore_dir: Optional[Path] = None) -> bool:
        """
        Restore a backup to the specified directory without overwriting anything.

        Symlinks that stay inside the restore directory are restored; links that point
        elsewhere, hardlinks and special files are skipped (see ``last_skipped``).

        :param backup_path: Path to the backup file
        :param restore_dir: Directory to restore to (defaults to current dir)
        :return: True if successful
        """
        self.last_skipped = []
        if not backup_path.exists():
            return False

        restore_dir = (restore_dir or Path.cwd()).expanduser().resolve()
        if not restore_dir.is_dir():
            return False

        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                extract = self._plan_restore(tar.getmembers(), restore_dir)
                if extract is None:
                    return False

                for member in extract:
                    if hasattr(tarfile, "data_filter"):
                        tar.extract(member, path=restore_dir, filter="data")
                    else:  # pragma: no cover - interpreters without extraction filters
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