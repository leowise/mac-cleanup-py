import os
from pathlib import Path
from typing import IO, Optional

import attr
from beartype import beartype  # pyright: ignore [reportUnknownVariableType]


# Redirection token -> (stream, target) assignments
_REDIRECTS = {
    ">/dev/null": (("stdout", "devnull"),),
    "1>/dev/null": (("stdout", "devnull"),),
    "2>/dev/null": (("stderr", "devnull"),),
    "&>/dev/null": (("stdout", "devnull"), ("stderr", "devnull")),
    ">&/dev/null": (("stdout", "devnull"), ("stderr", "devnull")),
    "2>&1": (("stderr", "stdout"),),
    ">&2": (("stdout", "stderr"),),
    "1>&2": (("stdout", "stderr"),),
}
_FORBIDDEN_TOKENS = {";", "||", "`", "$(", "${"}


def ensure_private_dir(path: Path) -> None:
    """Create ``path`` readable only by its owner, tightening it if it already exists."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def open_private(path: Path, mode: str = "a") -> IO[str]:
    """Open a text file for writing or appending, creating it readable only by its owner."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if "a" in mode else os.O_TRUNC)
    return os.fdopen(os.open(path, flags, 0o600), mode, encoding="utf-8")


@attr.s(slots=True)
class _Stage:
    """One program in a pipeline with its (shell-style) redirections."""

    argv: list[str] = attr.ib(factory=list)
    stdout: Optional[str] = attr.ib(default=None)  # "devnull" | "stderr"
    stderr: Optional[str] = attr.ib(default=None)  # "devnull" | "stdout"


def _parse_command(command: str) -> list[list[_Stage]]:
    """
    Parse a command into ``&&``-separated pipelines of stages without invoking a shell.

    Supported operators are the unquoted tokens ``|`` and ``&&`` plus the redirections
    ``>/dev/null``, ``2>/dev/null``, ``&>/dev/null``, ``2>&1`` and ``>&2``. Everything else
    is an inert argument. Validation and execution share this parser, so what is checked
    is exactly what runs.

    :raises ValueError: On malformed commands or forbidden operators
    """
    import shlex

    sequence: list[list[_Stage]] = [[_Stage()]]
    for token in shlex.split(command):
        if token in _FORBIDDEN_TOKENS:
            raise ValueError(f"Operator not supported: {token}")

        stage = sequence[-1][-1]
        if token == "|":
            sequence[-1].append(_Stage())
        elif token == "&&":
            sequence.append([_Stage()])
        elif token in _REDIRECTS:
            for stream, target in _REDIRECTS[token]:
                setattr(stage, stream, target)
        else:
            stage.argv.append(token)

    if any(not stage.argv for pipeline in sequence for stage in pipeline):
        raise ValueError("Empty command in pipeline")

    return sequence


def _run_pipeline(stages: list[_Stage], *, ignore_errors: bool, deadline: float) -> tuple[int, str, str]:
    """Run one pipeline; returns the last stage's exit code, stdout and stderr."""

    from subprocess import DEVNULL, PIPE, STDOUT, Popen, TimeoutExpired
    from time import monotonic

    processes: list[Popen[str]] = []
    try:
        for index, stage in enumerate(stages):
            is_last = index == len(stages) - 1

            discard_stdout = stage.stdout == "devnull" or (stage.stdout == "stderr" and ignore_errors)
            stdout = DEVNULL if discard_stdout else PIPE

            if stage.stderr == "devnull" or ignore_errors or not is_last:
                stderr = DEVNULL
            elif stage.stderr == "stdout":
                stderr = STDOUT
            else:
                stderr = PIPE

            process = Popen(
                stage.argv,
                shell=False,  # Never use a shell: operators are handled by _parse_command
                stdin=processes[-1].stdout if processes else None,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            # The next stage owns the read end now
            if processes and processes[-1].stdout:
                processes[-1].stdout.close()
            processes.append(process)

        stdout_text, stderr_text = processes[-1].communicate(timeout=max(deadline - monotonic(), 0.001))
        for process in processes[:-1]:
            process.wait(timeout=max(deadline - monotonic(), 0.001))
        return processes[-1].returncode, stdout_text or "", stderr_text or ""
    except TimeoutExpired:
        raise
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


def _run_with_retries(
    pipeline: list[_Stage], *, command: str, ignore_errors: bool, deadline: float, retries: int, retry_delay: float
) -> tuple[int, str, str]:
    """
    Run one pipeline, retrying non-zero exits with exponential backoff.

    Only this pipeline is retried, so earlier ``&&`` steps never run twice. Timeouts and
    exceptions propagate immediately, and no retry starts once the deadline would pass.
    """
    from time import monotonic, sleep

    from mac_cleanup.logger import logger

    for attempt in range(retries + 1):
        result = _run_pipeline(pipeline, ignore_errors=ignore_errors, deadline=deadline)
        delay = retry_delay * 2**attempt
        if result[0] == 0 or attempt == retries or monotonic() + delay >= deadline:
            break
        logger.log_operation(command, 0, "command_retry", False)
        sleep(delay)

    return result


@beartype
def cmd(
    command: str,
    *,
    ignore_errors: bool = True,
    timeout: int = 30,
    validate_command: bool = True,
    retries: int = 0,
    retry_delay: float = 0.5,
) -> str:
    """
    Executes a command (``|`` and ``&&`` supported) without a shell, with security enhancements.

    :param command: Command line
    :param ignore_errors: If True, no stderr in return and failures don't raise
    :param timeout: Command execution timeout in seconds
    :param validate_command: If True, validate command against whitelist
    :param retries: Extra attempts for a pipeline that exits non-zero (never for timeouts)
    :param retry_delay: Seconds before the first retry; doubles each time, within ``timeout``
    :return: stdout of executed command
    """
    from subprocess import TimeoutExpired
    from time import monotonic

    from mac_cleanup.errors import CommandError, CommandTimeoutError, CommandValidationError
    from mac_cleanup.logger import logger

    if timeout <= 0 or retries < 0:
        raise CommandValidationError("timeout must be greater than zero and retries cannot be negative")

    # Validate command if requested
    if validate_command and not _is_command_allowed(command):
        logger.log_operation(command, 0, "command_blocked", False)
        raise CommandValidationError(f"Command not allowed: {command}")

    try:
        sequence = _parse_command(command)
    except ValueError as e:
        logger.log_operation(command, 0, "command_parse_error", False)
        raise CommandValidationError(f"Invalid command format: {e}") from e

    deadline = monotonic() + timeout
    outputs: list[str] = []
    returncode, stderr = 0, ""

    try:
        for pipeline in sequence:
            returncode, stdout, stderr = _run_with_retries(
                pipeline, command=command, ignore_errors=ignore_errors, deadline=deadline,
                retries=retries, retry_delay=retry_delay,
            )
            outputs.append(stdout.strip())

            # '&&': later pipelines only run after success
            if returncode != 0:
                break
    except TimeoutExpired as e:
        logger.log_operation(command, 0, "command_timeout", False)
        raise CommandTimeoutError(f"Command timed out after {timeout} seconds: {command}", cause=e) from e
    except Exception as e:
        logger.log_operation(command, 0, "command_error", False)
        raise CommandError(f"Command execution failed: {e}", cause=e) from e

    logger.log_operation(command, 0, "command_executed", returncode == 0)

    if not ignore_errors and returncode != 0:
        raise CommandError(f"Command failed (exit code {returncode}): {stderr or 'Command failed'}")

    output = "\n".join(part for part in outputs if part)
    if not ignore_errors and stderr:
        output += "\n" + stderr.strip()

    return output.strip()


def _is_command_allowed(command: str) -> bool:
    """
    Check if command is in the allowed whitelist.

    :param command: Command to check
    :return: True if allowed
    """
    # Define allowed commands and patterns
    allowed_commands = {
        # Shell built-ins used for existence checks in default modules
        "type", "echo", "sleep",
        # System utilities
        "osascript", "xcrun", "defaults", "killall", "launchctl",
        "ps", "grep",  # used in default_modules (e.g. ps aux | grep '[T]elegram')
        # Development tools
        "brew", "npm", "yarn", "pnpm", "pip", "python", "ruby", "gem",
        "docker", "bun", "composer", "go", "pod", "poetry",
        # File operations (limited)
        "rm", "mv", "cp", "mkdir", "chmod", "chown",
        # Archive operations
        "tar", "gzip", "bzip2",
        # System information
        "sw_vers", "system_profiler", "diskutil", "df", "du",
        # Network
        "curl", "wget",
        # Development
        "git", "make", "cmake"
    }

    # Dangerous commands that should be blocked
    dangerous_commands = {
        "sudo", "su", "passwd", "chpasswd", "usermod", "userdel", "groupmod",
        "mount", "umount", "fdisk", "mkfs", "dd", "format",
        "shutdown", "reboot", "halt", "poweroff",
        "crontab", "at", "batch",
        "ssh", "scp", "ftp", "telnet"  # Network access (except curl/wget which are allowed)
    }

    try:
        sequence = _parse_command(command)
    except ValueError:
        return False

    def executable_allowed(value: str) -> bool:
        if value.startswith("/"):
            resolved = Path(value).resolve()
            allowed_directories = {"/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin", "/sbin"}
            if resolved.parent.as_posix() not in allowed_directories:
                return False
            value = resolved.name
        if value in dangerous_commands:
            return False
        return value in allowed_commands

    # Every program of every pipeline must be allowed; all other tokens are inert arguments
    try:
        return all(executable_allowed(stage.argv[0]) for pipeline in sequence for stage in pipeline)
    except OSError:
        return False


@beartype
def expanduser(str_path: str) -> str:
    """
    Expands user.

    :param str_path: Path to be expanded
    :return: Path with extended user path as a posix
    """

    from pathlib import Path

    return Path(str_path).expanduser().as_posix()


@beartype
def check_exists(path: Path | str, *, expand_user: bool = True) -> bool:
    """
    Checks if path exists.

    :param path: Path to be checked
    :param expand_user: True if path needs to be expanded
    :return: True if specified path exists
    """

    if not isinstance(path, Path):
        path = Path(path)

    if expand_user:
        path = path.expanduser()

    # If glob return True (it'll delete nothing at the end, hard to handle otherwise)
    if "*" in path.as_posix():
        return True

    return path.exists()


@beartype
def check_deletable(path: Path | str) -> bool:
    """
    Checks if path is deletable using enhanced path validation.

    :param path: Path to be deleted
    :return: True if specified path is deletable
    """
    # Convert path to correct type
    if not isinstance(path, Path):
        path_: Path = Path(path)
    else:
        path_ = path

    # Handle special cases (from original implementation)
    path_posix = path_.as_posix()

    # Returns False if empty
    if path_posix == ".":
        return False

    from mac_cleanup.path_validator import path_validator

    # Use the new path validator for comprehensive security checks
    validation_result = path_validator.validate_path(path, check_size=False)

    # Path is deletable if it's valid (allowed and not blocked)
    return validation_result.get("valid", False)


@beartype
def bytes_to_human(size_bytes: int | float) -> str:
    """
    Converts bytes to human-readable format.

    :param size_bytes: Bytes
    :return: Human readable size
    """

    from math import floor, log

    if size_bytes <= 0:
        return "0B"

    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(floor(log(size_bytes, 1024)))
    p = pow(1024, i)
    s = round(size_bytes / p, 2)

    return f"{s} {size_name[i]}"
