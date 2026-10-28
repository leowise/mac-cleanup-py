"""Modal yes/no dialog for questions the cleanup engine asks mid-run."""

import re

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

_MARKUP = re.compile(r"\[/?[a-z_ ]*\]")


def plain(text: str) -> str:
    """Strip the engine's rich markup tags (e.g. ``[danger]``), which Textual does not know."""

    return _MARKUP.sub("", text)


class ConfirmScreen(ModalScreen[bool]):
    """Ask whether to go ahead; ``n`` / escape decline, so the safe answer is the easy one."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Vertical { width: 80%; max-width: 100; height: auto; padding: 1 2; border: thick $error; background: $surface; }
    ConfirmScreen #confirm-title { text-style: bold; margin-bottom: 1; }
    ConfirmScreen Horizontal { height: auto; margin-top: 1; align-horizontal: right; }
    """
    BINDINGS = [("y", "answer(True)", "Yes"), ("n", "answer(False)", "No"), ("escape", "answer(False)", "No")]

    def __init__(self, text: str, title: str) -> None:
        super().__init__()
        self._text = plain(text)
        self._title = plain(title)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, id="confirm-title")
            yield Static(self._text, markup=False)
            with Horizontal():
                yield Button("No (n)", id="no", variant="primary")
                yield Button("Yes (y)", id="yes", variant="error")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, answer: bool) -> None:
        self.dismiss(answer)
