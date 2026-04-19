from __future__ import annotations

from dataclasses import dataclass, field

from ..query import filter_unit_rows
from ..units import UnitRow


@dataclass(slots=True)
class UnitListState:
    all_rows: dict[str, UnitRow] = field(default_factory=dict)
    selected_ids: set[str] = field(default_factory=set)
    visible_ids: list[str] = field(default_factory=list)
    query_text: str = ""
    query_error: str | None = None
    focused_id: str | None = None

    def reload_rows(self, rows: list[UnitRow]) -> None:
        self.all_rows = {row.unit_id: row for row in rows}
        self.selected_ids = {
            unit_id for unit_id in self.selected_ids if unit_id in self.all_rows
        }
        if self.focused_id not in self.all_rows:
            self.focused_id = None
        self.apply_query(self.query_text)

    def apply_query(self, query: str) -> None:
        self.query_text = query
        rows = list(self.all_rows.values())
        try:
            filtered = filter_unit_rows(rows, query)
            self.visible_ids = [row.unit_id for row in filtered]
            self.query_error = None
            if self.focused_id not in self.visible_ids:
                self.focused_id = self.visible_ids[0] if self.visible_ids else None
        except ValueError as exc:
            self.query_error = str(exc)

    def toggle_selected(self, unit_id: str) -> None:
        if unit_id in self.selected_ids:
            self.selected_ids.remove(unit_id)
        else:
            self.selected_ids.add(unit_id)

    def select_visible(self) -> None:
        for unit_id in self.visible_ids:
            self.selected_ids.add(unit_id)

    def unselect_visible(self) -> None:
        for unit_id in self.visible_ids:
            self.selected_ids.discard(unit_id)

    @property
    def selected_visible_count(self) -> int:
        visible = set(self.visible_ids)
        return len([unit_id for unit_id in self.selected_ids if unit_id in visible])

    @property
    def selected_hidden_count(self) -> int:
        visible = set(self.visible_ids)
        return len([unit_id for unit_id in self.selected_ids if unit_id not in visible])
