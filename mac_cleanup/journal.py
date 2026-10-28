"""Append-only journal of deletions, used to detect runs that died mid-deletion."""

import json
import os
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from mac_cleanup.operation import OperationStatus

MAX_LINES = 1000


class OperationJournal:
    """
    Records the status of every path operation, one JSON object per line.

    A deletion is journaled as ``backed_up`` before the command runs and as ``completed``,
    ``failed`` or ``rolled_back`` afterwards. A path whose last entry is still ``backed_up``
    in a *different* run was interrupted: the process died between backup and deletion.
    """

    def __init__(self) -> None:
        self._file = Path.home() / ".mac_cleanup_logs" / "operations.jsonl"
        self._run_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{os.getpid()}"

    def record(self, path: str, status: OperationStatus, backup: Optional[str] = None) -> None:
        """Append one entry; journaling must never break a cleanup, so errors are ignored."""
        entry = {
            "time": datetime.now().isoformat(),
            "run": self._run_id,
            "path": path,
            "status": status.value,
            "backup": backup,
        }
        with suppress(OSError):
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with self._file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            self._trim()

    def _trim(self) -> None:
        """Keep the journal bounded by dropping the oldest entries."""
        lines = self._file.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            self._file.write_text("\n".join(lines[-MAX_LINES // 2 :]) + "\n", encoding="utf-8")

    def _entries(self) -> list[dict[str, Any]]:
        try:
            lines = self._file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        entries: list[dict[str, Any]] = []
        for line in lines:
            with suppress(ValueError):
                entry = json.loads(line)
                if isinstance(entry, dict):
                    entries.append(entry)  # pyright: ignore [reportUnknownArgumentType]
        return entries

    def interrupted(self) -> list[dict[str, Any]]:
        """Operations from earlier runs that were backed up but never finished or reported."""
        last: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in self._entries():
            last[(str(entry.get("run")), str(entry.get("path")))] = entry

        return [
            entry
            for (run, _), entry in last.items()
            if entry.get("status") == OperationStatus.BACKED_UP.value and run != self._run_id
        ]

    def acknowledge(self, entries: list[dict[str, Any]]) -> None:
        """Mark interrupted operations as reported so they are not shown again."""
        for entry in entries:
            with suppress(OSError):
                reported = {**entry, "status": OperationStatus.INTERRUPTED.value, "time": datetime.now().isoformat()}
                line = json.dumps(reported)
                with self._file.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")


journal = OperationJournal()
