"""Every statically declared default-module path must pass the cleanup whitelist."""

import re
from pathlib import Path

import mac_cleanup.default_modules as default_modules
from mac_cleanup.path_validator import PathValidator

_PATH_CALL = re.compile(r'Path\(\s*f?"([^"]+)"')


def _static_default_paths() -> list[str]:
    source = Path(default_modules.__file__).read_text(encoding="utf-8")
    # Skip dynamic f-string interpolations; they are resolved at runtime.
    return sorted({p for p in _PATH_CALL.findall(source) if "{" not in p})


def test_default_module_paths_are_whitelisted() -> None:
    validator = PathValidator()
    rejected = [p for p in _static_default_paths() if not validator.validate_path(p, check_size=False)["valid"]]
    assert rejected == []


def test_whitelist_still_rejects_broad_and_critical_paths() -> None:
    validator = PathValidator()
    for path in (
        "~",
        "~/*",
        "~/Library/*",
        "~/Documents/anything",
        "~/Music/Music Library",
        "~/Downloads/file.zip",
        "/System/Library",
        "/Library/Preferences",
        "/Volumes/Backup/data",
        "/usr/local/bin",
    ):
        assert not validator.validate_path(path, check_size=False)["valid"], path


def test_wildcard_allowlist_matches_by_path_segment() -> None:
    validator = PathValidator()
    assert validator.validate_path("~/Library/Containers/com.x/Data/Library/Caches/a", check_size=False)["valid"]
    assert not validator.validate_path("~/Library/Containers/com.x/Data/Documents", check_size=False)["valid"]
    # '*' must not span path separators
    assert not validator.validate_path("~/Library/Containers/a/b/Data/Library/Caches", check_size=False)["valid"]


def test_non_star_glob_pattern_does_not_crash() -> None:
    validator = PathValidator()
    validator.add_allowed_path("~/scratch/[ab]cache")
    assert validator.validate_path("~/scratch/acache/x", check_size=False)["valid"]
