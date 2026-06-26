"""Async bridge between TUI and the sync cleanup engine."""

import asyncio
from dataclasses import dataclass, field
from os import statvfs
from pathlib import Path
from typing import Callable, Optional

from mac_cleanup.core import _Collector


@dataclass
class ModuleResult:
    name: str
    status: str  # "done" | "error" | "skipped"
    error: Optional[str] = None


@dataclass
class CleanupResult:
    module_results: list[ModuleResult] = field(default_factory=list)
    total_bytes_freed: float = 0.0
    dry_run: bool = False


OnStartCallback = Callable[[str], None]
OnCompleteCallback = Callable[[ModuleResult], None]


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

                if not dry_run:
                    collector = _Collector()
                    for unit in collector._execute_list:  # noqa: SLF001
                        for mod in unit.modules:
                            try:
                                mod._execute()  # noqa: SLF001
                            except Exception:
                                pass

                mod_result = ModuleResult(name=module_name, status="done")
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
    ) -> CleanupResult:
        """Run cleanup in a thread, reporting progress via callbacks."""
        return await asyncio.to_thread(
            self._run_sync, enabled_modules, dry_run, on_start, on_complete
        )
