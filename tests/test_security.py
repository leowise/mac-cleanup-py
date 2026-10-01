"""Security-focused tests for mac_cleanup_py."""

import pytest
from pathlib import Path
from unittest.mock import patch


class TestCommandSecurity:
    """Test command execution security features."""

    def test_allowed_commands(self):
        """Test that allowed commands pass validation."""
        from mac_cleanup.utils import _is_command_allowed

        allowed_commands = [
            "brew", "npm", "yarn", "pip", "python",
            "git", "rm", "mv", "cp", "mkdir",
            "tar", "gzip", "curl", "wget"
        ]

        for cmd in allowed_commands:
            assert _is_command_allowed(cmd), f"Command {cmd} should be allowed"

    def test_blocked_commands(self):
        """Test that dangerous commands are blocked."""
        from mac_cleanup.utils import _is_command_allowed

        dangerous_commands = [
            "sudo", "su", "passwd", "mount", "umount",
            "fdisk", "mkfs", "dd", "shutdown", "reboot",
            "ssh", "scp", "ftp", "telnet"
        ]

        for cmd in dangerous_commands:
            assert not _is_command_allowed(cmd), f"Command {cmd} should be blocked"

    def test_command_injection_prevention(self):
        """Test that command injection attempts are prevented."""
        from mac_cleanup.utils import cmd

        # These should fail due to command validation
        with pytest.raises(ValueError, match="Command not allowed"):
            cmd("sudo rm -rf /", validate_command=True)

        with pytest.raises(ValueError, match="Command not allowed"):
            cmd("ssh hacker@example.com", validate_command=True)

    def test_command_timeout(self):
        """Test that commands timeout properly."""
        from mac_cleanup.utils import cmd
        import time

        start_time = time.time()
        with pytest.raises(TimeoutError):
            # This should timeout quickly
            cmd("sleep 10", timeout=1, validate_command=False)
        end_time = time.time()

        # Should timeout within reasonable time
        assert end_time - start_time < 3, "Command should timeout quickly"

    def test_malformed_command_rejection(self):
        """Test that malformed commands are rejected."""
        from mac_cleanup.utils import cmd

        with pytest.raises(ValueError, match="Invalid command format"):
            cmd("", validate_command=False)

        with pytest.raises(ValueError, match="Invalid command format"):
            cmd('unclosed "quote', validate_command=False)


class TestPathSecurity:
    """Test path validation security features."""

    def test_critical_paths_blocked(self):
        """Test that critical system paths are blocked."""
        from mac_cleanup.utils import check_deletable

        critical_paths = [
            "/System", "/usr", "/bin", "/sbin", "/private",
            "/Library", "/Applications"
        ]

        for path in critical_paths:
            assert not check_deletable(path), f"Path {path} should be blocked"

    def test_user_critical_paths_blocked(self):
        """Test that critical user paths are blocked when expanded."""
        from mac_cleanup.utils import check_deletable

        # These should be blocked when expanded
        critical_user_paths = [
            "~/Desktop", "~/Documents", "~/Downloads",
            "~/Pictures", "~/Movies", "~/Music"
        ]

        for path_str in critical_user_paths:
            expanded_path = Path(path_str).expanduser()
            assert not check_deletable(expanded_path), f"Expanded path {expanded_path} should be blocked"

    def test_safe_paths_allowed(self):
        """Test that safe cleanup paths are allowed."""
        from mac_cleanup.utils import check_deletable

        safe_paths = [
            "~/Library/Caches", "/tmp", "/var/tmp",
            "~/Library/Logs", "~/.Trash"
        ]

        for path in safe_paths:
            assert check_deletable(path), f"Path {path} should be allowed"

    def test_glob_patterns_allowed(self):
        """Test that glob patterns are allowed."""
        from mac_cleanup.utils import check_deletable

        allowed_glob_patterns = ["~/Library/Caches/*", "/tmp/*"]

        for pattern in allowed_glob_patterns:
            assert check_deletable(pattern), f"Glob pattern {pattern} should be allowed"

        assert not check_deletable("*"), "Unscoped glob patterns must be rejected"

    def test_empty_path_blocked(self):
        """Test that empty paths are blocked."""
        from mac_cleanup.utils import check_deletable

        assert not check_deletable(""), "Empty string should be blocked"
        assert not check_deletable("."), "Current directory should be blocked"


class TestPathValidator:
    """Test the PathValidator class directly."""

    def test_path_validator_initialization(self):
        """Test that PathValidator initializes with correct defaults."""
        from mac_cleanup.path_validator import PathValidator

        validator = PathValidator()

        # Should have default allowed paths
        assert len(validator.allowed_paths) > 0
        assert len(validator.blocked_paths) > 0

        # Should have default size limits
        assert validator.size_limits["warning_threshold"] == 100 * 1024 * 1024  # 100MB
        assert validator.size_limits["block_threshold"] == 1024 * 1024 * 1024   # 1GB

    def test_add_remove_allowed_paths(self):
        """Test adding and removing allowed paths."""
        from mac_cleanup.path_validator import PathValidator

        validator = PathValidator()

        # Add a path
        validator.add_allowed_path("/test/path")
        assert "/test/path" in validator.user_allowed_paths

        # Remove a path
        validator.remove_allowed_path("/test/path")
        assert "/test/path" not in validator.user_allowed_paths

    def test_size_limit_validation(self):
        """Test size limit validation."""
        from mac_cleanup.path_validator import PathValidator

        validator = PathValidator()

        # Create a temporary file for testing
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Write some data
            f.write(b"x" * 1000)  # 1KB file
            temp_path = f.name

        try:
            result = validator.validate_path(temp_path, check_size=True)
            assert result["valid"], "Small file should be valid"
            assert len(result["size_info"]["warnings"]) == 0, "Small file should have no warnings"

        finally:
            os.unlink(temp_path)

    def test_large_file_warnings(self):
        """Test that large files generate warnings."""
        from mac_cleanup.path_validator import PathValidator

        validator = PathValidator()

        # Create a large temporary file
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Write data larger than warning threshold (100MB)
            f.write(b"x" * (150 * 1024 * 1024))  # 150MB
            temp_path = f.name

        try:
            result = validator.validate_path(temp_path, check_size=True)
            assert result["valid"], "Large file should still be valid but with warnings"
            assert len(result["size_info"]["warnings"]) > 0, "Large file should have warnings"

        finally:
            os.unlink(temp_path)


class TestModuleSecurity:
    """Test custom module security features."""

    def test_safe_module_accepted(self):
        """Test that safe modules are accepted."""
        from mac_cleanup.module_security import validate_custom_module
        import tempfile

        safe_code = '''"""Safe custom module."""
from mac_cleanup import *

clc = Collector()

def cleanup():
    """Safe cleanup function."""
    from mac_cleanup.utils import check_exists
    if check_exists("~/Library/Caches/test"):
        with clc as unit:
            unit.message("Safe cleanup")
            unit.add(Path("~/Library/Caches/test"))
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(safe_code)
            f.flush()
            result = validate_custom_module(f.name)
            assert result, "Safe module should be accepted"

    def test_dangerous_module_rejected(self):
        """Test that dangerous modules are rejected."""
        from mac_cleanup.module_security import validate_custom_module
        import tempfile

        dangerous_code = '''"""Dangerous custom module."""
import os
import subprocess

def cleanup():
    """Dangerous function with system calls."""
    os.system("rm -rf /")
    subprocess.call(["sudo", "rm", "-rf", "/"])
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(dangerous_code)
            f.flush()
            result = validate_custom_module(f.name)
            assert not result, "Dangerous module should be rejected"

    def test_malformed_module_rejected(self):
        """Test that malformed modules are rejected."""
        from mac_cleanup.module_security import validate_custom_module
        import tempfile

        malformed_code = '''"""Malformed custom module."""
def cleanup(
    # Syntax error - missing closing paren
    return "broken"
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(malformed_code)
            f.flush()
            result = validate_custom_module(f.name)
            assert not result, "Malformed module should be rejected"


class TestIntegrationSecurity:
    """Integration tests for security features."""

    def test_full_security_pipeline(self):
        """Test the complete security validation pipeline."""
        from mac_cleanup.core_modules import Command
        from mac_cleanup.core_modules import Path as CleanupPath

        # Test safe operations
        safe_command = Command("echo 'safe test'")
        safe_path = CleanupPath("~/Library/Caches/test")

        # These should work without issues
        assert safe_command is not None
        assert safe_path is not None

    def test_command_logging_on_failure(self):
        """Test that failed commands are properly logged."""
        from mac_cleanup.utils import cmd
        from mac_cleanup.logger import logger

        with patch.object(logger, "log_operation") as mock_log:
            # Use a command that will fail due to validation
            with pytest.raises(ValueError, match="Command not allowed"):
                cmd("sudo badcommand", validate_command=True)

            # Should log the command block
            mock_log.assert_called_with("sudo badcommand", 0, "command_blocked", False)

    def test_backup_before_dangerous_operations(self):
        """Test that backups are created before dangerous operations."""
        from mac_cleanup.backup import backup_manager

        # This is more of a smoke test - backup functionality should work
        backups = backup_manager.list_backups()
        assert isinstance(backups, list), "Should return a list of backups"