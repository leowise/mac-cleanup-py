from pathlib import Path

from beartype import beartype  # pyright: ignore [reportUnknownVariableType]


@beartype
def cmd(command: str, *, ignore_errors: bool = True, timeout: int = 30, validate_command: bool = True) -> str:
    """
    Executes command in Popen with security enhancements.

    :param command: Bash command
    :param ignore_errors: If True, no stderr in return
    :param timeout: Command execution timeout in seconds
    :param validate_command: If True, validate command against whitelist
    :return: stdout of executed command
    """
    import shlex
    from subprocess import TimeoutExpired

    # Validate command if requested
    if validate_command and not _is_command_allowed(command):
        from mac_cleanup.logger import logger
        logger.log_operation(command, 0, "command_blocked", False)
        raise ValueError(f"Command not allowed: {command}")

    # Sanitize command - prevent command injection by ensuring it's properly formed
    try:
        # Parse command to ensure it's safe
        parsed_command = shlex.split(command)
        if not parsed_command:
            raise ValueError("Empty command")
    except ValueError as e:
        from mac_cleanup.logger import logger
        logger.log_operation(command, 0, "command_parse_error", False)
        raise ValueError(f"Invalid command format: {e}") from e

    from subprocess import DEVNULL, PIPE, Popen

    process = None
    try:
        # Execute command with timeout
        process = Popen(
            parsed_command,
            shell=False,  # Use shell=False for better security
            stdout=PIPE,
            stderr=(DEVNULL if ignore_errors else PIPE),
            text=True  # Get text output directly
        )

        # Get stdout and stderr
        stdout, stderr = process.communicate(timeout=timeout)

        # Log command execution
        from mac_cleanup.logger import logger
        success = process.returncode == 0
        logger.log_operation(command, 0, "command_executed", success)

        # Handle errors
        if not ignore_errors and process.returncode != 0:
            error_output = stderr or "Command failed"
            raise RuntimeError(f"Command failed (exit code {process.returncode}): {error_output}")

        # Return combined output
        output = stdout or ""
        if not ignore_errors and stderr:
            output += "\n" + stderr

        return output.strip()

    except TimeoutExpired as e:
        from mac_cleanup.logger import logger
        logger.log_operation(command, 0, "command_timeout", False)
        # Kill the process if it times out
        if process:
            process.kill()
        raise TimeoutError(f"Command timed out after {timeout} seconds: {command}") from e
    except Exception as e:
        from mac_cleanup.logger import logger
        logger.log_operation(command, 0, "command_error", False)
        raise RuntimeError(f"Command execution failed: {e}") from e


def _is_command_allowed(command: str) -> bool:
    """
    Check if command is in the allowed whitelist.

    :param command: Command to check
    :return: True if allowed
    """
    # Define allowed commands and patterns
    allowed_commands = {
        # Shell built-ins used for existence checks in default modules
        "type",
        # System utilities
        "osascript", "xcrun", "defaults", "killall", "launchctl",
        # Development tools
        "brew", "npm", "yarn", "pnpm", "pip", "python", "ruby", "gem",
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

    import shlex

    try:
        parsed = shlex.split(command)
        if not parsed:
            return False

        base_command = parsed[0]

        # Check if command is in dangerous list
        if base_command in dangerous_commands:
            return False

        # Check if command is in allowed list or is a full path to allowed command
        if base_command in allowed_commands:
            return True

        # Allow full paths to system binaries
        allowed_paths = ["/bin/", "/usr/bin/", "/sbin/"]
        if any(base_command.startswith(path) for path in allowed_paths):
            allowed_basename = base_command.split("/")[-1]
            return allowed_basename in allowed_commands

        return False

    except ValueError:
        # If command can't be parsed, reject it
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

    # If glob return True (it'll delete nothing at the end, hard to handle otherwise)
    if "*" in path_posix:
        return True

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
