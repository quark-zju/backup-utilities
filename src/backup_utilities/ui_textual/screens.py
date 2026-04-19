from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Static


@dataclass(slots=True)
class DiscoverCandidate:
    unit_id: str
    info: str
    default_selected: bool


class TextPromptScreen(Screen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Back")]

    def __init__(
        self, title: str, prompt: str, default: str = "", *, password: bool = False
    ) -> None:
        super().__init__()
        self._title = title
        self._prompt = prompt
        self._default = default
        self._password = password

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt_root"):
            yield Static(self._title, id="prompt_title")
            yield Static(self._prompt, id="prompt_text")
            yield Input(value=self._default, id="prompt_input", password=self._password)
            yield Static("Enter: confirm | Esc: back", id="prompt_hint")

    def on_mount(self) -> None:
        self.query_one("#prompt_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmScreen(Screen[bool]):
    BINDINGS = [
        Binding("y", "yes", "Yes"),
        Binding("n", "no", "No"),
        Binding("enter", "yes", "Yes"),
        Binding("escape", "no", "Back"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_root"):
            yield Static("Confirm", id="confirm_title")
            yield Static(self._message, id="confirm_text")
            yield Static("Y/Enter: confirm | N/Esc: cancel", id="confirm_hint")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class DiscoverSelectScreen(Screen[list[str] | None]):
    BINDINGS = [
        Binding("space", "toggle", "Toggle"),
        Binding("a", "all", "All"),
        Binding("n", "none", "None"),
        Binding("enter", "confirm", "Add"),
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(self, candidates: list[DiscoverCandidate]) -> None:
        super().__init__()
        self._candidates = candidates
        self._selected: set[str] = {c.unit_id for c in candidates if c.default_selected}
        self._visible_ids: list[str] = [c.unit_id for c in candidates]

    def compose(self) -> ComposeResult:
        yield Static("Discover Result", id="discover_title")
        yield DataTable(id="discover_table")
        yield Static(
            "Space: toggle | A: all | N: none | Enter: confirm add | Esc: cancel/back",
            id="discover_hint",
        )

    def on_mount(self) -> None:
        table = self.query_one("#discover_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Select", "Unit", "Info")
        self._render_table()

    def _render_table(self) -> None:
        table = self.query_one("#discover_table", DataTable)
        table.clear(columns=False)
        for candidate in self._candidates:
            mark = self._selection_marker(candidate.unit_id)
            table.add_row(mark, candidate.unit_id, candidate.info)

    def _selection_marker(self, unit_id: str) -> str:
        return "x" if unit_id in self._selected else ""

    def _update_selection_cell(self, unit_id: str) -> None:
        if unit_id not in self._visible_ids:
            return
        row_index = self._visible_ids.index(unit_id)
        table = self.query_one("#discover_table", DataTable)
        table.update_cell_at(
            Coordinate(row_index, 0),
            self._selection_marker(unit_id),
        )

    def _update_all_selection_cells(self) -> None:
        table = self.query_one("#discover_table", DataTable)
        for row_index, unit_id in enumerate(self._visible_ids):
            table.update_cell_at(
                Coordinate(row_index, 0),
                self._selection_marker(unit_id),
            )

    def _current_unit_id(self) -> str | None:
        table = self.query_one("#discover_table", DataTable)
        row_index = table.cursor_row
        if row_index is None:
            return None
        if row_index < 0 or row_index >= len(self._visible_ids):
            return None
        return self._visible_ids[row_index]

    def action_toggle(self) -> None:
        unit_id = self._current_unit_id()
        if not unit_id:
            return
        if unit_id in self._selected:
            self._selected.remove(unit_id)
        else:
            self._selected.add(unit_id)
        self._update_selection_cell(unit_id)

    def action_all(self) -> None:
        self._selected = set(self._visible_ids)
        self._update_all_selection_cells()

    def action_none(self) -> None:
        self._selected.clear()
        self._update_all_selection_cells()

    def action_confirm(self) -> None:
        self.dismiss(sorted(self._selected))

    def action_cancel(self) -> None:
        self.dismiss(None)
