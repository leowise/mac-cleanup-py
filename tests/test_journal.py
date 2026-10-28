"""Crash-recovery journal for cleanup operations."""

from pathlib import Path

import pytest

from mac_cleanup.backup import backup_manager
from mac_cleanup.core_modules import Path as CleanupPath
from mac_cleanup.journal import MAX_LINES, OperationJournal, journal
from mac_cleanup.operation import OperationStatus


def _journal(tmp_path: Path, run: str) -> OperationJournal:
    j = OperationJournal()
    j._file = tmp_path / "ops.jsonl"
    j._run_id = run
    return j


def test_backed_up_operation_from_another_run_is_reported_as_interrupted(tmp_path: Path) -> None:
    crashed = _journal(tmp_path, "run1")
    crashed.record("/a", OperationStatus.BACKED_UP, backup="/b/a.tar.gz")
    crashed.record("/done", OperationStatus.BACKED_UP, backup="/b/d.tar.gz")
    crashed.record("/done", OperationStatus.COMPLETED)

    later = _journal(tmp_path, "run2")
    interrupted = later.interrupted()
    assert [(e["path"], e["backup"]) for e in interrupted] == [("/a", "/b/a.tar.gz")]


def test_current_run_is_not_interrupted(tmp_path: Path) -> None:
    j = _journal(tmp_path, "run1")
    j.record("/a", OperationStatus.BACKED_UP)
    assert j.interrupted() == []


def test_acknowledged_operations_are_not_reported_again(tmp_path: Path) -> None:
    _journal(tmp_path, "run1").record("/a", OperationStatus.BACKED_UP)
    later = _journal(tmp_path, "run2")
    later.acknowledge(later.interrupted())
    assert later.interrupted() == []
    assert _journal(tmp_path, "run3").interrupted() == []


def test_corrupt_and_missing_journal_are_tolerated(tmp_path: Path) -> None:
    j = _journal(tmp_path, "run1")
    assert j.interrupted() == []
    j._file.write_text("not json\n[1, 2]\n", encoding="utf-8")
    assert j.interrupted() == []


def test_journal_is_bounded(tmp_path: Path) -> None:
    j = _journal(tmp_path, "run1")
    for i in range(MAX_LINES + 50):
        j.record(f"/p{i}", OperationStatus.COMPLETED)
    assert len(j._file.read_text().splitlines()) <= MAX_LINES


def test_path_operation_journals_each_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "work" / "remove-me"
    target.parent.mkdir()
    target.write_text("data")
    monkeypatch.setattr("mac_cleanup.core_modules.args.force", True)
    monkeypatch.setattr("mac_cleanup.core_modules.args.safe_delete", False)

    CleanupPath(str(target))._execute()
    statuses = [e["status"] for e in journal._entries() if e["path"] == target.as_posix()]
    assert statuses == ["backed_up", "completed"]
    assert journal.interrupted() == []
    assert backup_manager.list_backups()


def test_crash_between_backup_and_delete_is_detected_next_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "work" / "remove-me"
    target.parent.mkdir()
    target.write_text("data")
    monkeypatch.setattr("mac_cleanup.core_modules.args.force", True)
    monkeypatch.setattr("mac_cleanup.core_modules.args.safe_delete", False)

    def die(command: str, **_: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("mac_cleanup.core_modules.cmd", die)
    with pytest.raises(KeyboardInterrupt):
        CleanupPath(str(target))._execute()

    monkeypatch.setattr(journal, "_run_id", "next-run")
    interrupted = journal.interrupted()
    assert [e["path"] for e in interrupted] == [target.as_posix()]
    assert Path(interrupted[0]["backup"]).exists()


def test_start_reports_interrupted_run_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from mac_cleanup.main import EntryPoint

    journal.record("/crashed/path", OperationStatus.BACKED_UP, backup="/b/x.tar.gz")
    monkeypatch.setattr(journal, "_run_id", "later-run")

    EntryPoint.report_interrupted()
    out = capsys.readouterr().out
    assert "/crashed/path" in out
    assert "/b/x.tar.gz" in out

    EntryPoint.report_interrupted()
    assert capsys.readouterr().out == ""
