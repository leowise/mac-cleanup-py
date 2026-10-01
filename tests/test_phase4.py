"""Focused coverage for Phase 4 safety and resumability behavior."""

from pathlib import Path

import toml

from mac_cleanup.config import Config
from mac_cleanup.core_modules import Path as CleanupPath
from mac_cleanup.module_security import load_custom_module_safely, validate_custom_module
from mac_cleanup.operation import OperationStatus
from mac_cleanup.path_validator import PathValidator


def test_path_validator_rejects_unscoped_and_symlinked_paths(tmp_path: Path) -> None:
    """Allow only scoped cleanup paths and do not let symlinks bypass them."""
    validator = PathValidator()
    assert not validator.validate_path(Path.home() / "anything")["valid"]

    safe_target = tmp_path / "safe"
    safe_target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(safe_target, target_is_directory=True)
    validator.add_allowed_path(str(safe_target))
    result = validator.validate_path(link)
    assert result["valid"]


def test_custom_module_loader_validates_and_loads(tmp_path: Path) -> None:
    """Load a validated module and refuse dangerous or symlinked files."""
    module_file = tmp_path / "custom.py"
    module_file.write_text("def cleanup():\n    return 'ok'\n", encoding="utf-8")
    module = load_custom_module_safely(str(module_file))
    assert module is not None
    assert module.cleanup() == "ok"

    dangerous = tmp_path / "dangerous.py"
    dangerous.write_text("import subprocess\n", encoding="utf-8")
    assert not validate_custom_module(str(dangerous), show_warnings=False)

    link = tmp_path / "linked.py"
    link.symlink_to(module_file)
    assert not validate_custom_module(str(link), show_warnings=False)


def test_path_operation_is_idempotent_and_tracks_status(tmp_path: Path, monkeypatch) -> None:
    """A completed operation is safe to resume without executing twice."""
    target = tmp_path / "remove-me"
    target.write_text("data", encoding="utf-8")
    operation = CleanupPath(str(target))
    monkeypatch.setattr("mac_cleanup.core_modules.args.force", True)

    operation._execute()
    assert operation.operation_status is OperationStatus.COMPLETED
    assert operation._execute() is None
    assert not target.exists()


def test_environment_configuration_avoids_prompt(tmp_path: Path, monkeypatch) -> None:
    """Environment variables can provide configuration for non-interactive runs."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(toml.dumps({"enabled": [], "custom_path": None}), encoding="utf-8")
    monkeypatch.setenv("MAC_CLEANUP_ENABLED_MODULES", "cleanup_a, cleanup_b")
    config = Config(config_file)
    assert config.get_config_data["enabled"] == ["cleanup_a", "cleanup_b"]
