"""Enhanced path validation with whitelist approach and size limits."""

import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, List, Set, Union

from beartype import beartype  # pyright: ignore [reportUnknownVariableType]

from mac_cleanup.console import console
from mac_cleanup.utils import expanduser


class PathValidationError(Exception):
    """Exception raised when path validation fails."""


class PathValidator:
    """Enhanced path validator with whitelist approach and size limits."""

    # Default allowed paths for cleanup operations
    DEFAULT_ALLOWED_PATHS = {
        # User cache directories
        "~/Library/Caches",
        "~/Library/Application Support",
        "~/Library/Logs",
        "~/Library/Containers/*/Data/Library/Caches",
        "~/Library/Group Containers/*/Library/Caches",
        # System cache directories (limited)
        "/private/var/folders",  # User temp files
        "/tmp",
        "/var/tmp",
        "/private/var/log",
        "/Library/Logs",
        # Trash
        "~/.Trash",
        "/Volumes/*/.Trashes",
        # User-specific directories that are safe to clean
        "~/Downloads/temp",
        "~/Desktop/temp",
    }

    # Paths that should never be touched
    CRITICAL_PATHS = {
        "/System", "/usr", "/bin", "/sbin", "/private",
        "/Library", "/Applications", "/Volumes",
        # Block expanded user paths for critical directories
        "~/Desktop", "~/Documents", "~/Downloads",
        "~/Pictures", "~/Movies", "~/Music"
    }

    # Size limits (in bytes)
    DEFAULT_SIZE_LIMITS = {
        "warning_threshold": 100 * 1024 * 1024,  # 100MB - warn user
        "block_threshold": 1024 * 1024 * 1024,   # 1GB - block operation
        "max_individual_file": 1024 * 1024 * 1024, # 1GB per file (same as block_threshold)
    }

    def __init__(self):
        self.allowed_paths: Set[str] = set()
        self.blocked_paths: Set[str] = set()
        self.size_limits = self.DEFAULT_SIZE_LIMITS.copy()
        self.user_allowed_paths: Set[str] = set()

        # Initialize with defaults
        self._load_default_paths()

    def _load_default_paths(self) -> None:
        """Load default allowed and blocked paths."""
        # Add default allowed paths
        for path_pattern in self.DEFAULT_ALLOWED_PATHS:
            expanded = expanduser(path_pattern)
            self.allowed_paths.add(expanded)

        # Add critical blocked paths
        for path_pattern in self.CRITICAL_PATHS:
            expanded = expanduser(path_pattern)
            self.blocked_paths.add(expanded)

    @beartype
    def add_allowed_path(self, path: str) -> None:
        """
        Add a user-defined allowed path.

        :param path: Path pattern to allow
        """
        expanded = expanduser(path)
        self.user_allowed_paths.add(expanded)
        console.print(f"[info]Added allowed path: {path}[/info]")

    @beartype
    def remove_allowed_path(self, path: str) -> None:
        """
        Remove a user-defined allowed path.

        :param path: Path pattern to remove
        """
        expanded = expanduser(path)
        self.user_allowed_paths.discard(expanded)
        console.print(f"[info]Removed allowed path: {path}[/info]")

    @beartype
    def validate_path(self, path: Union[str, Path], *, check_size: bool = True) -> Dict[str, Any]:
        """
        Validate a path for cleanup operations.

        :param path: Path to validate
        :param check_size: Whether to check size limits
        :return: Validation result with details
        """
        if isinstance(path, str):
            path = Path(path)

        # Expand and normalize before applying either the blocklist or whitelist.
        expanded_path = path.expanduser()
        lexical_path_str = expanded_path.as_posix()
        original_path_str = lexical_path_str
        has_glob = any(char in original_path_str for char in "*?[")
        if not has_glob:
            expanded_path = expanded_path.resolve(strict=False)
        else:
            # Resolve the non-pattern portion so a symlink cannot bypass the list.
            prefix = original_path_str
            wildcard_index = min((prefix.find(char) for char in "*?[" if prefix.find(char) >= 0), default=len(prefix))
            wildcard_prefix = prefix[:wildcard_index]
            parent = Path(wildcard_prefix or ".").resolve(strict=False)
            original_path_str = (parent / prefix[wildcard_index:]).as_posix()

        result: Dict[str, Any] = {
            "valid": False,
            "reason": "",
            "warnings": [],
            "size_info": None
        }

        # Block critical paths before checking the whitelist. Keep the lexical
        # spelling so safe aliases such as /tmp are not mistaken for /private.
        if self._is_blocked_path(lexical_path_str):
            result["reason"] = f"Path is in critical system areas: {lexical_path_str}"
            return result

        if not self._is_allowed_path(original_path_str):
            result["reason"] = f"Path is outside the cleanup whitelist: {original_path_str}"
            return result

        result["valid"] = True

        # Check size limits if requested
        if check_size and expanded_path.exists():
            size_info = self._check_size_limits(expanded_path)
            result["size_info"] = size_info

            if size_info["blocked"]:
                result["reason"] = size_info["reason"]
                return result

            if size_info["warnings"]:
                result["warnings"].extend(size_info["warnings"])

        # Check for symlinks and aliases
        if expanded_path.is_symlink():
            result["warnings"].append("Path is a symlink - target will be affected")

        result["valid"] = True
        return result

    def _is_blocked_path(self, path_str: str) -> bool:
        """Check if path is in the blocked list."""
        for blocked in self.blocked_paths:
            if not (path_str.startswith(blocked + "/") or path_str == blocked):
                continue
            # /private contains explicitly approved temporary/log subtrees;
            # retain the broad block for everything else.
            if blocked == "/private" and path_str != blocked and self._is_allowed_path(path_str):
                continue
            return True
        return False

    def _is_allowed_path(self, path_str: str) -> bool:
        """Check if path is in the allowed list."""
        # Check user-defined allowed paths first
        for allowed in self.user_allowed_paths:
            if self._matches_pattern(path_str, allowed):
                return True

        # Check default allowed paths
        return any(self._matches_pattern(path_str, allowed) for allowed in self.allowed_paths)

    def _matches_pattern(self, path_str: str, pattern: str) -> bool:
        """Check a normalized path against an allowlist pattern safely."""
        pattern = Path(pattern).expanduser().as_posix()
        if any(char in pattern for char in "*?["):
            prefix, suffix = pattern.split("*", 1)
            canonical_prefix = Path(prefix).resolve(strict=False).as_posix()
            pattern = canonical_prefix + "*" + suffix
            candidate = Path(path_str).resolve(strict=False).as_posix()
            return fnmatch.fnmatchcase(candidate, pattern)
        canonical_pattern = Path(pattern).resolve(strict=False).as_posix()
        candidate = Path(path_str).resolve(strict=False).as_posix()
        return candidate == canonical_pattern or candidate.startswith(canonical_pattern.rstrip("/") + "/")

    def _check_size_limits(self, path: Path) -> Dict[str, Any]:
        """Check size limits for a path."""
        result: Dict[str, Any] = {
            "total_size": 0,
            "file_count": 0,
            "blocked": False,
            "warnings": [],
            "reason": ""
        }

        try:
            if path.is_file():
                size = path.stat().st_size
                result["total_size"] = size
                result["file_count"] = 1

                if size > self.size_limits["max_individual_file"]:
                    result["blocked"] = True
                    result["reason"] = (
                        f"Individual file too large: {size} bytes "
                        f"(limit: {self.size_limits['max_individual_file']})"
                    )
                elif size > self.size_limits["warning_threshold"]:
                    result["warnings"].append(
                        f"Large file detected: {size} bytes "
                        f"(warning threshold: {self.size_limits['warning_threshold']})"
                    )

            elif path.is_dir():
                total_size = 0
                file_count = 0

                # Walk directory tree to calculate size
                for root, _dirs, files in os.walk(path):
                    for file in files:
                        try:
                            file_path = Path(root) / file
                            total_size += file_path.stat().st_size
                            file_count += 1

                            # Check individual file size
                            if file_path.stat().st_size > self.size_limits["max_individual_file"]:
                                result["warnings"].append(
                                    f"Large file found: {file_path} "
                                    f"({file_path.stat().st_size} bytes)"
                                )

                        except (OSError, PermissionError):
                            continue  # Skip files we can't access

                result["total_size"] = total_size
                result["file_count"] = file_count

                # Check thresholds
                if total_size > self.size_limits["block_threshold"]:
                    result["blocked"] = True
                    result["reason"] = (
                        f"Total size too large: {total_size} bytes "
                        f"(limit: {self.size_limits['block_threshold']})"
                    )
                elif total_size > self.size_limits["warning_threshold"]:
                    result["warnings"].append(f"Large operation detected: {total_size} bytes")

        except (OSError, PermissionError) as e:
            result["warnings"].append(f"Could not check size: {e}")

        return result

    @beartype
    def set_size_limit(self, limit_type: str, size_bytes: int) -> None:
        """
        Set a size limit.

        :param limit_type: Type of limit ('warning_threshold', 'block_threshold', 'max_individual_file')
        :param size_bytes: Size in bytes
        """
        if limit_type in self.size_limits:
            self.size_limits[limit_type] = size_bytes
            console.print(f"[info]Set {limit_type} to {size_bytes} bytes[/info]")
        else:
            raise ValueError(f"Unknown limit type: {limit_type}")

    def get_allowed_paths(self) -> List[str]:
        """Get list of all allowed paths."""
        return sorted(self.allowed_paths | self.user_allowed_paths)

    def get_blocked_paths(self) -> List[str]:
        """Get list of all blocked paths."""
        return sorted(self.blocked_paths)


# Global path validator instance
path_validator = PathValidator()


@beartype
def validate_path_for_cleanup(path: Union[str, Path], *, check_size: bool = True) -> bool:
    """
    Validate a path for cleanup operations using the whitelist approach.

    :param path: Path to validate
    :param check_size: Whether to check size limits
    :return: True if path is safe for cleanup
    """
    result = path_validator.validate_path(path, check_size=check_size)

    if not result["valid"]:
        console.print(f"[danger]Path validation failed: {result['reason']}[/danger]")
        return False

    if result["warnings"]:
        for warning in result["warnings"]:
            console.print(f"[warning]⚠️  {warning}[/warning]")

    return True


@beartype
def add_allowed_cleanup_path(path: str) -> None:
    """
    Add a user-defined path to the allowed cleanup list.

    :param path: Path pattern to allow
    """
    path_validator.add_allowed_path(path)


@beartype
def get_cleanup_path_info(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Get detailed information about a path's cleanup eligibility.

    :param path: Path to check
    :return: Detailed validation information
    """
    return path_validator.validate_path(path, check_size=True)


# Global path validator instance
path_validator = PathValidator()