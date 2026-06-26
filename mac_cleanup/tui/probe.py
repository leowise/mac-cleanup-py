"""Probe module availability by calling each function and checking if it registers any work."""

from typing import Callable


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
        _Collector._shared_instance.clear()
        try:
            fn()
            execute_list = _Collector._shared_instance.get("_execute_list", [])
            if execute_list:
                available.append(name)
        except Exception:
            pass

    _Collector._shared_instance.clear()
    return sorted(available)
