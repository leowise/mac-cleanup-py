"""Keep every test away from the real ~/.mac_cleanup_* directories."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_home_state(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from mac_cleanup.backup import backup_manager
    from mac_cleanup.journal import journal
    from mac_cleanup.logger import logger

    state = tmp_path_factory.mktemp("state")
    backups = state / "backups"
    backups.mkdir()
    monkeypatch.setattr(backup_manager, "_backup_dir", backups)
    monkeypatch.setattr(logger, "_log_file", state / "deletion_log.txt")
    monkeypatch.setattr(journal, "_file", state / "operations.jsonl")
    assert isinstance(state, Path)
