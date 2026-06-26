# TUI Design — mac-cleanup-py

**Date:** 2026-06-26  
**Status:** Approved

## Summary

Add a Textual-based interactive TUI to mac-cleanup-py. The TUI is a new presentation layer only — the existing cleanup engine, config, and CLI subcommands are untouched. Launching `mac-cleanup` with no subcommand (or `mac-cleanup ui`) opens the TUI; all existing subcommands continue to work as before.

---

## Architecture

A new `mac_cleanup/tui/` package holds all Textual code.

```
mac_cleanup/
  tui/
    __init__.py
    app.py              ← main Textual App, owns screen transitions
    screens/
      selection.py      ← module checklist screen
      progress.py       ← live cleanup dashboard screen
      results.py        ← summary screen
    widgets/
      module_list.py    ← reusable checklist widget
```

The existing engine (`core.py`, `default_modules.py`, `config.py`, `backup.py`, `progress.py`) is not modified. The TUI drives the engine through a thin async bridge in `tui/app.py`.

---

## The Three Screens

### Screen 1: Module Selection

A scrollable checklist of all available modules (default + custom), grouped by category (browsers, dev tools, system, etc.). Each row shows the module name and a short description.

**Controls:**
- `space` — toggle module on/off
- `a` — select all, `n` — deselect all
- `d` — toggle dry-run mode (shown as a status badge in the header)
- `enter` / `r` — run cleanup with selected modules
- `q` — quit

Pre-populates from the user's existing config so saved preferences are respected.

### Screen 2: Live Progress Dashboard

Split layout:
- **Top:** overall progress bar + elapsed time
- **Middle:** scrolling list of modules with status icons (⏳ pending, ⚙️ running, ✓ done, ✗ skipped/error)
- **Bottom:** live log tail showing what's currently being deleted

### Screen 3: Results Summary

Displayed after cleanup completes:
- Total space freed (large, prominent)
- Per-module breakdown: space freed + status
- Warnings and errors highlighted in red

**Controls:** `r` to run again, `q` to quit, `b` to return to module selection

---

## Data Flow & Integration

1. **Selection → Core:** The module checklist writes the user's selection to the existing `Config` object. No new config format.

2. **Core → Progress Screen:** A new `CleanupRunner` class wraps `core.py` and accepts a status callback/queue. The runner executes synchronous cleanup code via `asyncio.to_thread` so it doesn't block the Textual event loop. The progress screen subscribes to the queue and updates widgets reactively.

3. **Results:** After the runner finishes, it returns a `CleanupResult` dataclass (module name, bytes freed, status, errors) that the results screen renders.

4. **Error handling:** Module exceptions are caught, surfaced as a red row in the progress screen, and included in the results summary. `core.py` remains unaware of the TUI.

---

## Dependencies & Compatibility

- **New dependency:** `textual>=0.60` — added to `pyproject.toml` as a main dependency
- **Python:** Textual requires 3.8+; project already targets 3.11+, no conflict
- **Existing CLI:** All subcommands (`cleanup`, `dry-run`, `restore`, `configure`, `custom-path`) preserved exactly. TUI launches only on bare `mac-cleanup` or `mac-cleanup ui`.
- **Tests:** New `tests/test_tui.py` using Textual's `Pilot` test client for headless screen/transition testing. Existing tests unaffected.

---

## Out of Scope

- MCP server / agentic tool integration
- Scheduled/automated runs
- Native macOS app (menu bar, windows)
- Changes to the cleanup engine logic
