"""Probe module availability by calling each function and checking if it registers any work."""

from typing import Callable


def _reset_collector() -> None:
    """Reset the Borg-pattern Collector to a clean state."""
    from mac_cleanup.core import _Collector

    _Collector._shared_instance.clear()
    _Collector()  # re-creates _execute_list in shared state


def probe_available_modules(modules: dict[str, Callable[..., None]]) -> list[str]:
    """
    Return sorted list of module names that are applicable on this system.

    Calls each module function and checks whether it added any entries to
    the Collector. Modules that find nothing (app not installed, path absent)
    add nothing and are excluded from the result.
    """
    from mac_cleanup.core import _Collector

    available: list[str] = []

    for name, fn in modules.items():
        _reset_collector()
        try:
            fn()
            collector = _Collector()
            if collector._execute_list:
                available.append(name)
        except Exception:
            pass

    _reset_collector()
    return sorted(available)
