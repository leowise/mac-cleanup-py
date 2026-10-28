"""Tests for TUI components."""
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

    with patch("mac_cleanup.tui.runner.statvfs") as mock_stat:
        mock_statvfs_result = MagicMock()
        mock_statvfs_result.f_bavail = 1000
        mock_statvfs_result.f_frsize = 4096
        mock_stat.return_value = mock_statvfs_result

        runner = CleanupRunner(config_path=config_path, module_fns=mock_modules)
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

    with patch("mac_cleanup.tui.runner.statvfs") as mock_stat:
        mock_stat.return_value = MagicMock(f_bavail=1000, f_frsize=4096)

        runner = CleanupRunner(config_path=config_path, module_fns={"bad": bad_module})
        await runner.run(
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

    with patch("mac_cleanup.tui.runner.statvfs") as mock_stat:
        mock_stat.return_value = MagicMock(f_bavail=1000, f_frsize=4096)

        runner = CleanupRunner(config_path=config_path, module_fns={})
        await runner.run(
            enabled_modules=["nonexistent"],
            dry_run=False,
            on_start=lambda _: None,
            on_complete=completed.append,
        )

    assert completed[0].status == "skipped"


# --- probe tests ---

from mac_cleanup.tui.probe import probe_available_modules  # noqa: E402


def test_probe_excludes_unavailable_modules():
    """Module that adds nothing (app not installed) is excluded."""
    def present_module():
        from mac_cleanup.core import ProxyCollector as Collector
        from mac_cleanup.core_modules import Path as CleanPath
        with Collector() as unit:
            unit.message("test")
            unit.add(CleanPath("~/.Trash/*"))

    def absent_module():
        pass  # checks existence, finds nothing, adds nothing

    result = probe_available_modules({"present": present_module, "absent": absent_module})
    assert "present" in result
    assert "absent" not in result


def test_probe_handles_module_exception():
    """Module that raises is treated as unavailable, not a crash."""
    def bad_module():
        raise RuntimeError("something went wrong")

    result = probe_available_modules({"bad": bad_module})
    assert "bad" not in result


# --- MacCleanupApp integration tests ---

from mac_cleanup.tui.app import MacCleanupApp  # noqa: E402
from mac_cleanup.tui.screens.selection import SelectionScreen  # noqa: E402


async def test_app_starts_on_selection_screen(tmp_path):
    app = MacCleanupApp(config_path=tmp_path / ".mac_cleanup_py")
    async with app.run_test() as pilot:
        await pilot.pause()  # let LoadingScreen worker finish
        await app.workers.wait_for_complete()
        assert isinstance(app.screen, SelectionScreen)


async def test_app_dry_run_toggle(tmp_path):
    app = MacCleanupApp(config_path=tmp_path / ".mac_cleanup_py")
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        screen = app.screen
        assert isinstance(screen, SelectionScreen)
        assert screen.dry_run is False
        await pilot.press("d")
        assert screen.dry_run is True


async def test_app_safe_delete_toggle(tmp_path):
    app = MacCleanupApp(config_path=tmp_path / ".mac_cleanup_py")
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        screen = app.screen
        assert isinstance(screen, SelectionScreen)
        assert screen.safe_delete is False
        await pilot.press("s")
        assert screen.safe_delete is True


async def test_app_quit_from_selection(tmp_path):
    app = MacCleanupApp(config_path=tmp_path / ".mac_cleanup_py")
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("q")
    # App exited cleanly — no exception raised


# --- ProgressScreen tests ---

from mac_cleanup.tui.screens.progress import ProgressScreen  # noqa: E402


def test_progress_screen_instantiates(tmp_path):
    screen = ProgressScreen(
        enabled_modules=["brew"],
        dry_run=False,
        config_path=tmp_path / ".mac_cleanup_py",
    )
    assert screen._enabled_modules == ["brew"]
    assert screen._dry_run is False


# --- ResultsScreen tests ---

from mac_cleanup.tui.screens.results import ResultsScreen  # noqa: E402


def test_results_screen_instantiates():
    result = CleanupResult(
        module_results=[
            ModuleResult(name="brew", status="done"),
            ModuleResult(name="npm", status="error", error="timeout"),
        ],
        total_bytes_freed=1024.0 * 1024 * 50,
        dry_run=False,
    )
    screen = ResultsScreen(result=result)
    assert screen._result.total_bytes_freed == 1024.0 * 1024 * 50


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


async def test_runner_applies_safe_delete_and_restores_flags(tmp_path):
    """The TUI's safe-delete choice must reach the engine, and flags must not leak afterwards."""
    from mac_cleanup.parser import args

    seen: list[tuple[bool, bool]] = []
    before = (args.safe_delete, args.force)

    def module():
        seen.append((args.safe_delete, args.force))

    with patch("mac_cleanup.tui.runner.statvfs") as mock_stat:
        mock_stat.return_value = MagicMock(f_bavail=1000, f_frsize=4096)
        runner = CleanupRunner(config_path=tmp_path / ".mac_cleanup_py", module_fns={"m": module})
        await runner.run(
            enabled_modules=["m"], dry_run=False, safe_delete=True, on_start=lambda _: None, on_complete=lambda _: None
        )

    # force: the user already confirmed on the summary screen, and rich prompts cannot run inside Textual
    assert seen == [(True, True)]
    assert (args.safe_delete, args.force) == before


async def test_runner_reports_errors_from_individual_commands(tmp_path):
    """A failing command inside a module is reported, not silently swallowed."""
    from mac_cleanup.core import _Collector

    completed: list[ModuleResult] = []

    class Failing:
        def _execute(self):
            raise RuntimeError("rm failed")

    def module():
        _Collector()._execute_list.append(MagicMock(modules=[Failing()]))

    with patch("mac_cleanup.tui.runner.statvfs") as mock_stat:
        mock_stat.return_value = MagicMock(f_bavail=1000, f_frsize=4096)
        runner = CleanupRunner(config_path=tmp_path / ".mac_cleanup_py", module_fns={"m": module})
        await runner.run(
            enabled_modules=["m"], dry_run=False, on_start=lambda _: None, on_complete=completed.append
        )

    assert completed[0].status == "error"
    assert "rm failed" in (completed[0].error or "")


async def test_runner_routes_engine_prompts_to_confirm_callback(tmp_path):
    """With a confirm callback the engine's prompts reach it, and force stays off so they are asked."""
    from mac_cleanup.parser import args
    from mac_cleanup.progress import ProgressBar

    asked: list[tuple[str, str]] = []
    seen: list[tuple[bool, bool]] = []

    def module():
        seen.append((args.force, ProgressBar.prompt("really?", "title")))

    def confirm(text: str, title: str) -> bool:
        asked.append((text, title))
        return False

    before = (args.force, ProgressBar.prompt_handler)
    with patch("mac_cleanup.tui.runner.statvfs") as mock_stat, patch.object(args, "force", False):
        mock_stat.return_value = MagicMock(f_bavail=1000, f_frsize=4096)
        runner = CleanupRunner(config_path=tmp_path / ".mac_cleanup_py", module_fns={"m": module})
        await runner.run(
            enabled_modules=["m"], dry_run=False, confirm=confirm, on_start=lambda _: None, on_complete=lambda _: None
        )

    assert asked == [("really?", "title")]
    assert seen == [(False, False)]
    assert ProgressBar.prompt_handler is before[1]


def test_confirm_screen_strips_engine_markup():
    from mac_cleanup.tui.screens.confirm import plain

    assert plain("[danger]⚠️  NO BACKUP[/danger] keep [1.5 GB]") == "⚠️  NO BACKUP keep [1.5 GB]"


@pytest.mark.parametrize(("key", "expected"), [("y", True), ("n", False), ("escape", False)])
async def test_confirm_screen_keys(key, expected):
    from textual.app import App

    from mac_cleanup.tui.screens.confirm import ConfirmScreen

    answers: list[bool] = []

    class Host(App[None]):
        def on_mount(self) -> None:
            self.push_screen(ConfirmScreen("[bold]Delete?[/bold]", "[danger]Title[/danger]"), answers.append)

    async with Host().run_test() as pilot:
        await pilot.press(key)
        await pilot.pause()

    assert answers == [expected]
