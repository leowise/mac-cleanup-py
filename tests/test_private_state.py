"""Backups, logs and the journal must only be readable by their owner."""

import os
import stat
from pathlib import Path

import pytest

from mac_cleanup.backup import BackupManager
from mac_cleanup.journal import OperationJournal
from mac_cleanup.logger import OperationLogger
from mac_cleanup.operation import OperationStatus


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(os, "umask", os.umask)  # keep the default umask (typically 022)
    return home


def test_backup_directory_and_archives_are_private(fake_home: Path, tmp_path: Path) -> None:
    manager = BackupManager()
    assert _mode(fake_home / ".mac_cleanup_backups") == 0o700

    source = tmp_path / "secret.txt"
    source.write_text("token")
    archive = manager.create_backup(source)
    assert archive is not None
    assert _mode(archive) == 0o600


def test_existing_world_readable_backups_are_tightened(fake_home: Path) -> None:
    backups = fake_home / ".mac_cleanup_backups"
    backups.mkdir(mode=0o755)
    old = backups / "run1__old_abc_20250101_000000.tar.gz"
    old.write_bytes(b"x")
    old.chmod(0o644)
    backups.chmod(0o755)

    BackupManager()
    assert _mode(backups) == 0o700
    assert _mode(old) == 0o600


def test_log_and_journal_are_private(fake_home: Path) -> None:
    logger = OperationLogger()
    logger.log_operation("/some/path", 1)
    assert _mode(fake_home / ".mac_cleanup_logs") == 0o700
    assert _mode(logger.get_log_path()) == 0o600

    journal = OperationJournal()
    journal.record("/some/path", OperationStatus.BACKED_UP)
    assert _mode(journal._file) == 0o600
    journal.acknowledge(journal._entries())
    assert _mode(journal._file) == 0o600
