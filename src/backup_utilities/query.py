from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import shlex

from .units import UnitRow


@dataclass(slots=True)
class _DateCondition:
    field: str
    op: str
    value: date


def filter_unit_rows(rows: list[UnitRow], query: str) -> list[UnitRow]:
    matcher = _build_matcher(query)
    return [row for row in rows if matcher(row)]


def _build_matcher(query: str):
    tokens = _split_tokens(query)
    text_tokens: list[str] = []
    date_conditions: list[_DateCondition] = []

    for token in tokens:
        cond = _parse_condition_token(token)
        if cond is None:
            text_tokens.append(token.casefold())
        else:
            date_conditions.append(cond)

    def _matches(row: UnitRow) -> bool:
        unit_id = row.unit_id.casefold()
        unit_label = row.unit_label.casefold()
        for token in text_tokens:
            if token not in unit_id and token not in unit_label:
                return False

        for cond in date_conditions:
            if cond.field == "mtime":
                ts_value = row.last_snapshot_time
            elif cond.field == "ctime":
                ts_value = row.last_verify_time
            else:
                return False

            row_date = _timestamp_to_local_date(ts_value)
            if row_date is None:
                return False
            if not _compare_dates(row_date, cond.op, cond.value):
                return False

        return True

    return _matches


def _split_tokens(query: str) -> list[str]:
    query = query.strip()
    if not query:
        return []
    try:
        return shlex.split(query)
    except ValueError as exc:
        raise ValueError(f"invalid query syntax: {exc}") from exc


def _parse_condition_token(token: str) -> _DateCondition | None:
    prefixes = ("mtime:", "ctime:")
    if not token.startswith(prefixes):
        return None

    field, expr = token.split(":", maxsplit=1)
    op = None
    for candidate in (">=", "<=", "!=", ">", "<", "="):
        if expr.startswith(candidate):
            op = candidate
            rhs = expr[len(candidate) :]
            break
    if op is None:
        raise ValueError(f"invalid condition operator in token: {token}")

    value = _parse_date(rhs)
    return _DateCondition(field=field, op=op, value=value)


def _parse_date(raw: str) -> date:
    text = raw.strip()
    parts = text.split("-")
    if len(parts) != 3:
        raise ValueError(f"invalid date format: {raw}")
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
    except ValueError as exc:
        raise ValueError(f"invalid date format: {raw}") from exc

    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"invalid date value: {raw}") from exc


def _timestamp_to_local_date(value: str | None) -> date | None:
    if not value:
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone().date()


def _compare_dates(lhs: date, op: str, rhs: date) -> bool:
    if op == ">":
        return lhs > rhs
    if op == ">=":
        return lhs >= rhs
    if op == "<":
        return lhs < rhs
    if op == "<=":
        return lhs <= rhs
    if op == "=":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    raise ValueError(f"unsupported operator: {op}")
