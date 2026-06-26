"""Scrollable checklist widget for selecting cleanup modules."""

from textual.widgets import SelectionList
from textual.widgets.selection_list import Selection


class ModuleList(SelectionList[str]):
    """Scrollable checklist of cleanup module names."""

    DEFAULT_CSS = """
    ModuleList {
        height: 1fr;
        border: solid $accent;
    }
    """

    def build_selections(
        self,
        all_modules: list[str],
        enabled_modules: list[str],
    ) -> list[Selection[str]]:
        """Build sorted Selection items, pre-checking enabled modules."""
        enabled_set = set(enabled_modules)
        return [
            Selection(name, name, initial_state=(name in enabled_set))
            for name in sorted(all_modules)
        ]
