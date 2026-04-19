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
    sort_column: str | None = None
    sort_desc: bool = False

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
            self._apply_sort()
            self.query_error = None
            if self.focused_id not in self.visible_ids:
                self.focused_id = self.visible_ids[0] if self.visible_ids else None
        except ValueError as exc:
            self.query_error = str(exc)

    def set_sort(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_column = column
            self.sort_desc = False
        self._apply_sort()

    def sort_summary(self) -> str | None:
        if self.sort_column is None:
            return None
        direction = "desc" if self.sort_desc else "asc"
        return f"{self.sort_column}:{direction}"

    def _apply_sort(self) -> None:
        if self.sort_column is None:
            return
        key_fn = self._sort_key_for_column(self.sort_column)
        self.visible_ids.sort(key=key_fn, reverse=self.sort_desc)

    def _sort_key_for_column(self, column: str):
        def _value(unit_id: str):
            row = self.all_rows[unit_id]
            if column == "selected":
                return 1 if row.selected else 0
            if column == "excluded":
                return 1 if row.excluded else 0
            if column == "unit_id":
                return row.unit_id.casefold()
            if column == "encrypt_policy":
                return row.encrypt_policy.casefold()
            if column == "last_snapshot_time":
                return self._nullable_str_key(row.last_snapshot_time)
            if column == "payload_size_bytes":
                return self._nullable_int_key(row.payload_size_bytes)
            if column == "last_verify_time":
                return self._nullable_str_key(row.last_verify_time)
            return row.unit_id.casefold()

        return _value

    @staticmethod
    def _nullable_str_key(value: str | None) -> tuple[int, str]:
        if value is None:
            return (1, "")
        return (0, value)

    @staticmethod
    def _nullable_int_key(value: int | None) -> tuple[int, int]:
        if value is None:
            return (1, 0)
        return (0, value)

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
