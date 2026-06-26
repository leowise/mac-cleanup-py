"""Tests for TUI components."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mac_cleanup.tui.runner import CleanupResult, CleanupRunner, ModuleResult


def test_module_result_defaults():
    r = ModuleResult(name="brew", status="done")
    assert r.name == "brew"
    assert r.status == "done"
    assert r.error is None


def test_cleanup_result_defaults():
    r = CleanupResult()
    assert r.module_results == []
    assert r.total_bytes_freed == 0.0
    assert r.dry_run is False


async def test_runner_calls_callbacks(tmp_path):
    """Runner calls on_start and on_complete for each module."""
    config_path = tmp_path / ".mac_cleanup_py"

    started: list[str] = []
    completed: list[ModuleResult] = []

    mock_modules = {"brew": MagicMock(), "npm": MagicMock()}

    with (
        patch("mac_cleanup.tui.runner.Config") as mock_cfg_cls,
        patch("mac_cleanup.tui.runner._Collector") as mock_col_cls,
        patch("mac_cleanup.tui.runner.statvfs") as mock_stat,
    ):
        mock_cfg = MagicMock()
        mock_cfg.get_modules = mock_modules
        mock_cfg_cls.return_value = mock_cfg

        mock_collector = MagicMock()
        mock_collector._execute_list = []
        mock_col_cls.return_value = mock_collector

        mock_statvfs_result = MagicMock()
        mock_statvfs_result.f_bavail = 1000
        mock_statvfs_result.f_frsize = 4096
        mock_stat.return_value = mock_statvfs_result

        runner = CleanupRunner(config_path=config_path)
        result = await runner.run(
            enabled_modules=["brew", "npm"],
            dry_run=True,
            on_start=started.append,
            on_complete=completed.append,
        )

    assert started == ["brew", "npm"]
    assert len(completed) == 2
    assert all(r.status == "done" for r in completed)
    assert isinstance(result, CleanupResult)
    assert result.dry_run is True


async def test_runner_handles_module_error(tmp_path):
    """Runner catches exceptions from module functions and marks them as error."""
    config_path = tmp_path / ".mac_cleanup_py"
    completed: list[ModuleResult] = []

    def bad_module():
        raise RuntimeError("boom")

    with (
        patch("mac_cleanup.tui.runner.Config") as mock_cfg_cls,
        patch("mac_cleanup.tui.runner._Collector"),
        patch("mac_cleanup.tui.runner.statvfs") as mock_stat,
    ):
        mock_cfg = MagicMock()
        mock_cfg.get_modules = {"bad": bad_module}
        mock_cfg_cls.return_value = mock_cfg
        mock_stat.return_value = MagicMock(f_bavail=1000, f_frsize=4096)

        runner = CleanupRunner(config_path=config_path)
        result = await runner.run(
            enabled_modules=["bad"],
            dry_run=False,
            on_start=lambda _: None,
            on_complete=completed.append,
        )

    assert completed[0].status == "error"
    assert "boom" in (completed[0].error or "")


async def test_runner_skips_missing_module(tmp_path):
    """Runner marks unknown module names as skipped."""
    config_path = tmp_path / ".mac_cleanup_py"
    completed: list[ModuleResult] = []

    with (
        patch("mac_cleanup.tui.runner.Config") as mock_cfg_cls,
        patch("mac_cleanup.tui.runner._Collector"),
        patch("mac_cleanup.tui.runner.statvfs") as mock_stat,
    ):
        mock_cfg = MagicMock()
        mock_cfg.get_modules = {}
        mock_cfg_cls.return_value = mock_cfg
        mock_stat.return_value = MagicMock(f_bavail=1000, f_frsize=4096)

        runner = CleanupRunner(config_path=config_path)
        await runner.run(
            enabled_modules=["nonexistent"],
            dry_run=False,
            on_start=lambda _: None,
            on_complete=completed.append,
        )

    assert completed[0].status == "skipped"


# --- ModuleList widget tests ---

from mac_cleanup.tui.widgets.module_list import ModuleList  # noqa: E402


def test_build_selections_marks_enabled():
    widget = ModuleList()
    selections = widget.build_selections(
        all_modules=["brew", "npm", "docker"],
        enabled_modules=["brew", "docker"],
    )
    names = [str(s.prompt) for s in selections]
    assert "brew" in names
    assert "npm" in names
    selected = {str(s.prompt) for s in selections if s.initial_state}
    assert selected == {"brew", "docker"}


def test_build_selections_sorted():
    widget = ModuleList()
    selections = widget.build_selections(
        all_modules=["npm", "brew", "docker"],
        enabled_modules=[],
    )
    names = [str(s.prompt) for s in selections]
    assert names == sorted(names)
