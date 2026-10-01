import io
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
