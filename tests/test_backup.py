import io
import os
import tarfile
from pathlib import Path

from mac_cleanup.backup import BackupManager


def test_restore_rejects_existing_destination(tmp_path: Path) -> None:
    manager = BackupManager()
    manager._backup_dir = tmp_path / "backups"
    manager._backup_dir.mkdir()

    source = tmp_path / "source"
    source.mkdir()
    (source / "item.txt").write_text("content")
    archive = manager.create_backup(source)
    assert archive is not None

    destination = tmp_path / "restore"
    destination.mkdir()
    (destination / "source").mkdir()
    assert manager.restore_backup(archive, destination) is False
    assert not (destination / "source" / "item.txt").exists()


def test_restore_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    manager = BackupManager()
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        payload = tarfile.TarInfo("../../outside.txt")
        payload.size = len(b"unsafe")
        tar.addfile(payload, io.BytesIO(b"unsafe"))

    destination = tmp_path / "restore"
    destination.mkdir()
    assert manager.restore_backup(archive, destination) is False
    assert not (tmp_path / "outside.txt").exists()


def test_restore_extracts_to_empty_directory(tmp_path: Path) -> None:
    manager = BackupManager()
    manager._backup_dir = tmp_path / "backups"
    manager._backup_dir.mkdir()

    source = tmp_path / "source"
    source.mkdir()
    (source / "item.txt").write_text("content")
    archive = manager.create_backup(source)
    assert archive is not None

    destination = tmp_path / "restore"
    destination.mkdir()
    assert manager.restore_backup(archive, destination) is True
    assert (destination / "source" / "item.txt").read_text() == "content"


def _manager(tmp_path: Path, run_id: str) -> BackupManager:
    manager = BackupManager()
    manager._backup_dir = tmp_path / "backups"
    manager._backup_dir.mkdir(exist_ok=True)
    manager._run_id = run_id
    return manager


def _backup(manager: BackupManager, tmp_path: Path, name: str) -> Path:
    source = tmp_path / name
    source.write_text(name)
    archive = manager.create_backup(source)
    assert archive is not None
    return archive


def test_retention_counts_runs_not_individual_backups(tmp_path: Path) -> None:
    runs = []
    for run in range(3):
        manager = _manager(tmp_path, f"run{run}")
        runs.append([_backup(manager, tmp_path, f"item{run}_{i}") for i in range(4)])
        # Backups were just made, so the newest backup defines a run's age
        import os
        import time
        for archive in runs[-1]:
            os.utime(archive, (time.time() + run, time.time() + run))

    assert manager.cleanup_old_backups(keep_count=2) == 4
    assert not any(a.exists() for a in runs[0])
    assert all(a.exists() for a in runs[1] + runs[2])


def test_current_run_is_never_pruned(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "current")
    archives = [_backup(manager, tmp_path, f"item{i}") for i in range(15)]
    assert manager.cleanup_old_backups(keep_count=1) == 0
    assert all(a.exists() for a in archives)


def test_retention_setting_precedence(tmp_path: Path, monkeypatch) -> None:
    manager = _manager(tmp_path, "r")
    assert manager.retention == 10
    manager.retention = 3
    assert manager.retention == 3
    monkeypatch.setenv("MAC_CLEANUP_BACKUP_RETENTION", "5")
    assert manager.retention == 5
    monkeypatch.setenv("MAC_CLEANUP_BACKUP_RETENTION", "nonsense")
    assert manager.retention == 3
    monkeypatch.setenv("MAC_CLEANUP_BACKUP_RETENTION", "0")
    assert manager.retention == 3


def test_create_backup_applies_retention(tmp_path: Path) -> None:
    old = _manager(tmp_path, "old")
    old_archive = _backup(old, tmp_path, "old_item")
    import os
    os.utime(old_archive, (1, 1))

    new = _manager(tmp_path, "new")
    new.retention = 1
    _backup(new, tmp_path, "new_item")
    assert not old_archive.exists()


def test_config_sets_backup_retention(tmp_path: Path, monkeypatch) -> None:
    import toml

    from mac_cleanup.backup import backup_manager
    from mac_cleanup.config import Config

    monkeypatch.setattr(backup_manager, "_retention", backup_manager._retention)
    monkeypatch.delenv("MAC_CLEANUP_BACKUP_RETENTION", raising=False)
    config_file = tmp_path / "config.toml"
    config_file.write_text(toml.dumps({"enabled": ["x"], "custom_path": "", "backup_retention": 4}))
    Config(config_file)
    assert backup_manager.retention == 4


def _archive(path: Path, members: list[tuple[str, str, str]]) -> Path:
    """Build a tar.gz from (kind, name, content-or-linkname) tuples."""
    with tarfile.open(path, "w:gz") as tar:
        for kind, name, value in members:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(value.encode())
                tar.addfile(info, io.BytesIO(value.encode()))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = value
                tar.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = value
                tar.addfile(info)
    return path


def test_restore_keeps_safe_relative_symlinks(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "a.tar.gz",
        [("dir", "cache", ""), ("file", "cache/real.txt", "data"), ("symlink", "cache/link", "real.txt")],
    )
    destination = tmp_path / "restore"
    destination.mkdir()
    manager = BackupManager()
    assert manager.restore_backup(archive, destination) is True
    assert (destination / "cache" / "link").is_symlink()
    assert (destination / "cache" / "link").read_text() == "data"
    assert manager.last_skipped == []


def test_restore_skips_symlinks_that_leave_the_restore_directory(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "a.tar.gz",
        [
            ("file", "keep.txt", "data"),
            ("symlink", "absolute", "/etc"),
            ("symlink", "escape", "../outside"),
            ("hardlink", "hard", "keep.txt"),
        ],
    )
    destination = tmp_path / "restore"
    destination.mkdir()
    manager = BackupManager()
    assert manager.restore_backup(archive, destination) is True
    assert (destination / "keep.txt").read_text() == "data"
    assert not os.path.lexists(destination / "absolute")
    assert not os.path.lexists(destination / "escape")
    assert not os.path.lexists(destination / "hard")
    assert sorted(manager.last_skipped) == ["absolute", "escape", "hard"]


def test_restore_never_writes_outside_through_an_archived_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = _archive(
        tmp_path / "a.tar.gz",
        [("symlink", "link", str(outside)), ("file", "link/payload.txt", "pwned")],
    )
    destination = tmp_path / "restore"
    destination.mkdir()
    BackupManager().restore_backup(archive, destination)
    assert list(outside.iterdir()) == []


def test_restore_refuses_writing_through_a_kept_symlink(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "a.tar.gz",
        [("dir", "sub", ""), ("symlink", "link", "sub"), ("file", "link/payload.txt", "x")],
    )
    destination = tmp_path / "restore"
    destination.mkdir()
    assert BackupManager().restore_backup(archive, destination) is False
    assert list(destination.iterdir()) == []


def test_restore_conflict_detects_dangling_symlink(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "a.tar.gz", [("file", "item.txt", "data")])
    destination = tmp_path / "restore"
    destination.mkdir()
    (destination / "item.txt").symlink_to(tmp_path / "missing")
    assert BackupManager().restore_backup(archive, destination) is False
