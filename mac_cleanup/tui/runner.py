"""Async bridge between TUI and the sync cleanup engine."""

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from os import statvfs
from pathlib import Path
from typing import Callable, Iterator, Optional

from mac_cleanup.core import _Collector
from mac_cleanup.parser import args


@dataclass
class ModuleResult:
    name: str
    status: str  # "done" | "error" | "skipped"
    error: Optional[str] = None
    bytes_estimate: float = 0.0


@dataclass
class CleanupResult:
    module_results: list[ModuleResult] = field(default_factory=list)
    total_bytes_freed: float = 0.0
    dry_run: bool = False


OnStartCallback = Callable[[str], None]
OnCompleteCallback = Callable[[ModuleResult], None]


@contextmanager
def _engine_flags(*, safe_delete: bool, dry_run: bool) -> Iterator[None]:
    """
    Apply the TUI's choices to the engine's global flags for one run, then restore them.

    ``force`` is set for real runs only: the user already confirmed on the dry-run summary
    screen, and the engine's rich prompts cannot run while Textual owns the terminal.
    """

    before = (args.safe_delete, args.force)
    args.safe_delete = safe_delete
    args.force = before[1] or not dry_run
    try:
        yield
    finally:
        args.safe_delete, args.force = before


class CleanupRunner:
    """Wraps the sync cleanup engine for use from an async Textual app."""

    def __init__(
        self,
        config_path: Path,
        module_fns: Optional[dict[str, Callable[..., None]]] = None,
    ) -> None:
        self._config_path = config_path
        self._module_fns = module_fns

    def _get_modules(self) -> dict[str, Callable[..., None]]:
        """Return module dict, loading from config only if not provided."""
        if self._module_fns is not None:
            return self._module_fns
        from mac_cleanup.config import Config
        _Collector._shared_instance.clear()
        _Collector()
        config = Config(config_path_=self._config_path)
        return config.get_modules

    def _run_sync(
        self,
        enabled_modules: list[str],
        dry_run: bool,
        on_start: OnStartCallback,
        on_complete: OnCompleteCallback,
        safe_delete: bool = False,
    ) -> CleanupResult:
        with _engine_flags(safe_delete=safe_delete, dry_run=dry_run):
            return self._run_modules(enabled_modules, dry_run, on_start, on_complete)

    def _run_modules(
        self,
        enabled_modules: list[str],
        dry_run: bool,
        on_start: OnStartCallback,
        on_complete: OnCompleteCallback,
    ) -> CleanupResult:
        all_modules = self._get_modules()

        result = CleanupResult(dry_run=dry_run)
        free_before = float(statvfs("/").f_bavail * statvfs("/").f_frsize)

        for module_name in enabled_modules:
            module_fn = all_modules.get(module_name)
            if module_fn is None:
                mod_result = ModuleResult(name=module_name, status="skipped")
                result.module_results.append(mod_result)
                on_complete(mod_result)
                continue

            on_start(module_name)

            try:
                _Collector._shared_instance.clear()
                _Collector()
                module_fn()

                collector = _Collector()
                module_bytes: float = 0.0
                failures: list[str] = []

                if dry_run:
                    for _path, size in collector._extract_paths():  # noqa: SLF001
                        module_bytes += size
                else:
                    for unit in collector._execute_list:  # noqa: SLF001
                        for mod in unit.modules:
                            try:
                                mod._execute()  # noqa: SLF001
                            except Exception as exc:
                                failures.append(str(exc))

                # Keep going after a failed command, but never report it as success
                mod_result = ModuleResult(
                    name=module_name,
                    status="error" if failures else "done",
                    error="; ".join(failures[:3]) if failures else None,
                    bytes_estimate=module_bytes,
                )
            except Exception as exc:
                mod_result = ModuleResult(name=module_name, status="error", error=str(exc))

            result.module_results.append(mod_result)
            on_complete(mod_result)

        free_after = float(statvfs("/").f_bavail * statvfs("/").f_frsize)
        result.total_bytes_freed = max(0.0, free_after - free_before)
        return result

    async def run(
        self,
        enabled_modules: list[str],
        dry_run: bool,
        on_start: OnStartCallback,
        on_complete: OnCompleteCallback,
        safe_delete: bool = False,
    ) -> CleanupResult:
        """Run cleanup in a thread, reporting progress via callbacks."""
        return await asyncio.to_thread(
            self._run_sync, enabled_modules, dry_run, on_start, on_complete, safe_delete
        )
