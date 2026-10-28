"""Size limit, status transitions and rollback for cleanup path operations."""

from pathlib import Path

import pytest

from mac_cleanup.backup import backup_manager
from mac_cleanup.core_modules import Path as CleanupPath
from mac_cleanup.logger import logger
from mac_cleanup.operation import OperationStatus
from mac_cleanup.path_validator import path_validator

MODULE = "mac_cleanup.core_modules"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep backups and logs out of the real home directory and avoid prompts."""
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(backup_manager, "_backup_dir", backups)
    monkeypatch.setattr(logger, "_log_file", tmp_path / "log.txt")
    monkeypatch.setattr(f"{MODULE}.args.force", True)
    monkeypatch.setattr(f"{MODULE}.args.safe_delete", False)
    monkeypatch.setattr(f"{MODULE}.args.no_size_limit", False)
    return tmp_path


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "work" / "remove-me"
    target.parent.mkdir()
    target.write_text("data", encoding="utf-8")
    return target


def _oversized(monkeypatch: pytest.MonkeyPatch, answers: list[bool]) -> list[str]:
    """Make every path oversized and script the confirmation prompt; returns prompt texts."""
    monkeypatch.setitem(path_validator.size_limits, "block_threshold", 1)
    monkeypatch.setattr(f"{MODULE}.args.force", False)
    prompts: list[str] = []

    def fake_prompt(*, prompt_text: str, **_: object) -> bool:
        prompts.append(prompt_text)
        return answers.pop(0)

    monkeypatch.setattr("mac_cleanup.progress.ProgressBar.prompt", staticmethod(fake_prompt))
    return prompts


def test_oversized_path_warns_and_respects_declined_confirmation(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _target(isolated_state)
    prompts = _oversized(monkeypatch, [False, True])

    operation = CleanupPath(str(target))
    assert operation._execute() is None
    assert target.exists()
    assert operation.operation_status is OperationStatus.SKIPPED
    assert "deletion limit" in prompts[0]

    # Declining is retryable; confirming deletes
    operation._execute()
    assert not target.exists()
    assert operation.operation_status is OperationStatus.COMPLETED


def test_oversized_path_with_force_proceeds_without_prompt(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _target(isolated_state)
    prompts = _oversized(monkeypatch, [])
    monkeypatch.setattr(f"{MODULE}.args.force", True)

    CleanupPath(str(target))._execute()
    assert prompts == []
    assert not target.exists()


def test_no_size_limit_suppresses_the_size_warning(isolated_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _target(isolated_state)
    prompts = _oversized(monkeypatch, [True])
    monkeypatch.setattr(f"{MODULE}.args.no_size_limit", True)

    CleanupPath(str(target))._execute()
    assert "deletion limit" not in prompts[0]
    assert not target.exists()


def test_check_deletable_does_not_enforce_size_limit(isolated_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mac_cleanup.utils import check_deletable

    target = _target(isolated_state)
    monkeypatch.setitem(path_validator.size_limits, "block_threshold", 1)
    assert check_deletable(target)


def test_backed_up_state_is_visible_while_command_runs(isolated_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _target(isolated_state)
    operation = CleanupPath(str(target))
    seen: list[OperationStatus] = []

    def fake_cmd(command: str, **_: object) -> str:
        seen.append(operation.operation_status)
        target.unlink()
        return ""

    monkeypatch.setattr(f"{MODULE}.cmd", fake_cmd)
    operation._execute()
    assert seen == [OperationStatus.BACKED_UP]
    assert operation.operation_status is OperationStatus.COMPLETED


def test_declined_prompt_is_skipped_and_retryable(isolated_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _target(isolated_state)
    operation = CleanupPath(str(target))
    monkeypatch.setattr(f"{MODULE}.BaseModule._execute", lambda self: False)

    assert operation._execute() is None
    assert operation.operation_status is OperationStatus.SKIPPED
    assert not operation.operation_status.terminal
    assert target.exists()
    assert list(backup_manager.get_backup_dir().iterdir()) == []

    monkeypatch.undo()
    monkeypatch.setattr(f"{MODULE}.args.force", True)
    operation._execute()
    assert operation.operation_status is OperationStatus.COMPLETED


def test_failed_command_that_removed_target_is_rolled_back(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _target(isolated_state)
    operation = CleanupPath(str(target))

    def failing_cmd(command: str, **_: object) -> str:
        target.unlink()
        raise RuntimeError("boom")

    monkeypatch.setattr(f"{MODULE}.cmd", failing_cmd)
    with pytest.raises(RuntimeError):
        operation._execute()

    assert operation.operation_status is OperationStatus.ROLLED_BACK
    assert target.read_text(encoding="utf-8") == "data"


def test_command_that_leaves_target_behind_is_failed_and_retryable(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _target(isolated_state)
    operation = CleanupPath(str(target))
    monkeypatch.setattr(f"{MODULE}.cmd", lambda command, **_: "")

    operation._execute()
    assert operation.operation_status is OperationStatus.FAILED
    assert not operation.operation_status.terminal
    assert target.exists()


def _glob_dir(tmp_path: Path) -> Path:
    base = tmp_path / "cache"
    base.mkdir()
    (base / "a.txt").write_text("a")
    (base / "b.txt").write_text("b")
    (base / "sub").mkdir()
    (base / "sub" / "c.txt").write_text("c")
    (base / ".hidden").write_text("h")
    return base


def test_glob_path_actually_deletes_matches(isolated_state: Path) -> None:
    base = _glob_dir(isolated_state)
    operation = CleanupPath(str(base / "*"))

    operation._execute()
    # Like a shell glob, '*' does not match dotfiles
    assert sorted(p.name for p in base.iterdir()) == [".hidden"]
    assert operation.operation_status is OperationStatus.COMPLETED


def test_glob_path_is_backed_up_and_restorable(isolated_state: Path) -> None:
    base = _glob_dir(isolated_state)
    CleanupPath(str(base / "*"))._execute()

    archives = backup_manager.list_backups()
    assert len(archives) == 1
    assert backup_manager.restore_backup(archives[0]["path"], backup_manager.restore_root(base / "*"))
    assert (base / "a.txt").read_text() == "a"
    assert (base / "sub" / "c.txt").read_text() == "c"


def test_glob_without_matches_is_skipped_quietly(isolated_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = isolated_state / "empty"
    empty.mkdir()
    prompts = _oversized(monkeypatch, [])
    operation = CleanupPath(str(empty / "*"))

    assert operation._execute() is None
    assert operation.operation_status is OperationStatus.SKIPPED
    assert prompts == []
    assert backup_manager.list_backups() == []


def test_glob_matches_failing_validation_are_left_alone(isolated_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _glob_dir(isolated_state)
    real = __import__("mac_cleanup.utils", fromlist=["check_deletable"]).check_deletable
    monkeypatch.setattr(f"{MODULE}.check_deletable", lambda path: Path(path).name != "b.txt" and real(path))

    operation = CleanupPath(str(base / "*"))
    operation._execute()
    assert (base / "b.txt").exists()
    assert not (base / "a.txt").exists()
    assert operation.operation_status is OperationStatus.FAILED


def test_failed_glob_command_that_removed_everything_is_rolled_back(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    base = _glob_dir(isolated_state)
    operation = CleanupPath(str(base / "*"))

    def failing_cmd(command: str, **_: object) -> str:
        for child in [p for p in base.iterdir() if p.name != ".hidden"]:
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        raise RuntimeError("boom")

    monkeypatch.setattr(f"{MODULE}.cmd", failing_cmd)
    with pytest.raises(RuntimeError):
        operation._execute()
    assert operation.operation_status is OperationStatus.ROLLED_BACK
    assert (base / "sub" / "c.txt").read_text() == "c"


def test_failed_backup_leaves_no_partial_archive(isolated_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tarfile

    base = _glob_dir(isolated_state)

    def broken_add(self, *args: object, **kwargs: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(tarfile.TarFile, "add", broken_add)
    assert backup_manager.create_backup(base / "*") is None
    assert list(backup_manager.get_backup_dir().iterdir()) == []


def test_restore_root_is_the_literal_directory_before_the_first_wildcard(tmp_path: Path) -> None:
    root = backup_manager.restore_root
    assert root(Path("/a/b/*")) == Path("/a/b")
    assert root(Path("/a/b/c*/d")) == Path("/a/b")
    assert root(Path("/a/b/[!x]*")) == Path("/a/b")
    assert root(Path("/a/b/file")) == Path("/a/b")
    assert root(Path("/*.hprof")) == Path("/")


@pytest.mark.parametrize("name", ["x' 'VICTIM", "x' '-rf' 'VICTIM", "x' 'VICTIM' '", 'x" VICTIM', "x; VICTIM"])
def test_hostile_file_names_cannot_inject_arguments(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """A file name must never become extra rm arguments (relative ones resolve against the cwd)."""
    cwd = isolated_state / "cwd"
    cwd.mkdir()
    victim = cwd / "VICTIM"
    victim.write_text("keep")
    monkeypatch.chdir(cwd)

    base = isolated_state / "cache"
    base.mkdir()
    (base / name).write_text("x")

    try:
        CleanupPath(str(base / "*"))._execute()
    finally:
        assert victim.read_text() == "keep"
    assert not (base / name).exists()


def test_safe_delete_command_passes_path_as_an_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{MODULE}.args.safe_delete", True)
    command = CleanupPath._delete_command(Path('/tmp/a" & quit & "b'))
    assert "on run argv" in command
    assert '/tmp/a" & quit & "b' not in command.replace("'/tmp/a\" & quit & \"b'", "")
