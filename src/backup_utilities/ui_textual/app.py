from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import sys
import traceback

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

from ..config import load_config
from ..discovery import discover_units
from ..protocols import default_registry
from ..runner import run_backup
from ..selectors import select_add, select_decrypt, select_encrypt, select_remove
from ..units import UnitRow, collect_unit_rows
from .screens import (
    ConfirmScreen,
    DiscoverCandidate,
    DiscoverSelectScreen,
    TextPromptScreen,
)
from .state import UnitListState


def _fmt_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "-"
    value = float(size_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    while value >= 1024 and unit_idx < len(units) - 1:
        value /= 1024
        unit_idx += 1
    if unit_idx == 0:
        return f"{int(value)} {units[unit_idx]}"
    return f"{value:.1f} {units[unit_idx]}"


def _fmt_ts(value: str | None) -> str:
    if not value:
        return "-"
    return value


class BackupTextualApp(App[None]):
    CSS = """
    #topbar {
      height: 3;
    }
    #search {
      width: 1fr;
    }
    #status {
      height: 2;
      padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("tab", "toggle_focus", "Focus"),
        Binding("space", "toggle_row", "Toggle"),
        Binding("a", "select_visible", "Select Visible"),
        Binding("n", "unselect_visible", "Unselect Visible"),
        Binding("b", "backup_selected", "Backup"),
        Binding("e", "encrypt_selected", "Encrypt"),
        Binding("d", "decrypt_selected", "Decrypt"),
        Binding("x", "remove_selected", "Remove"),
        Binding("m", "add_manual", "Add Manual"),
        Binding("f", "discover_add", "Discover Add"),
        Binding("r", "reload_units", "Reload"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._protocol_registry = default_registry()
        self._state = UnitListState()

    def _fatal_error(self) -> None:
        if os.environ.get("BACKUP_PLAIN_TRACEBACK") == "1":
            error = self._exception
            if error is not None:
                traceback.print_exception(
                    type(error),
                    error,
                    error.__traceback__,
                    file=sys.stderr,
                )
            else:
                traceback.print_exc(file=sys.stderr)
            self._close_messages_no_wait()
            return
        super()._fatal_error()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="topbar"):
            yield Input(
                placeholder="Search: text, mtime:>2026-1-1, ctime:>=2026-1-1",
                id="search",
            )
        yield DataTable(id="units_table")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#units_table", DataTable)
        table.cursor_type = "row"
        table.add_columns(
            "Sel",
            "Unit ID",
            "Encrypt Policy",
            "Last Snapshot Time",
            "Payload Size",
            "Last Verify Time",
        )
        self.action_reload_units()

    def _capture_call(self, fn, *args, **kwargs):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return fn(*args, **kwargs)

    def _render_table(self, preferred_unit_id: str | None = None) -> None:
        if preferred_unit_id is None:
            preferred_unit_id = self._state.focused_id or self._current_unit_id()
        self._state.focused_id = preferred_unit_id

        table = self.query_one("#units_table", DataTable)
        table.clear(columns=False)
        for unit_id in self._state.visible_ids:
            row = self._state.all_rows[unit_id]
            marker = "x" if unit_id in self._state.selected_ids else ""
            table.add_row(
                marker,
                row.unit_id,
                row.encrypt_policy,
                _fmt_ts(row.last_snapshot_time),
                _fmt_size(row.payload_size_bytes),
                _fmt_ts(row.last_verify_time),
            )
        self._restore_cursor(preferred_unit_id)
        self._render_status()

    def _render_status(self, message: str | None = None) -> None:
        status = self.query_one("#status", Static)
        total = len(self._state.all_rows)
        visible = len(self._state.visible_ids)
        selected = len(self._state.selected_ids)
        hidden = self._state.selected_hidden_count

        chunks = [
            f"total={total} visible={visible} selected={selected} hidden_selected={hidden}"
        ]
        if self._state.query_error:
            chunks.append(f"query_error={self._state.query_error}")
        if message:
            chunks.append(message)
        status.update(" | ".join(chunks))

    def _current_unit_id(self) -> str | None:
        table = self.query_one("#units_table", DataTable)
        row_index = table.cursor_row
        if row_index is None:
            return None
        if row_index < 0 or row_index >= len(self._state.visible_ids):
            return None
        return self._state.visible_ids[row_index]

    def _restore_cursor(self, preferred_unit_id: str | None) -> None:
        table = self.query_one("#units_table", DataTable)
        if not self._state.visible_ids:
            self._state.focused_id = None
            return

        target_id = preferred_unit_id
        if target_id not in self._state.visible_ids:
            target_id = self._state.visible_ids[0]

        target_index = self._state.visible_ids.index(target_id)
        table.move_cursor(row=target_index, animate=False, scroll=False)
        self._state.focused_id = target_id

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "units_table":
            return
        row = event.cursor_row
        if row < 0 or row >= len(self._state.visible_ids):
            return
        self._state.focused_id = self._state.visible_ids[row]

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search":
            return
        keep_id = self._state.focused_id or self._current_unit_id()
        prev_visible = list(self._state.visible_ids)
        self._state.apply_query(event.value)
        if self._state.query_error:
            self._state.visible_ids = prev_visible
        self._render_table(preferred_unit_id=keep_id)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_table(self) -> None:
        self.query_one("#units_table", DataTable).focus()

    def action_toggle_focus(self) -> None:
        search = self.query_one("#search", Input)
        if search.has_focus:
            self.action_focus_table()
        else:
            self.action_focus_search()

    def on_key(self, event: events.Key) -> None:
        search = self.query_one("#search", Input)
        if search.has_focus and event.key in {"escape", "down"}:
            self.action_focus_table()
            event.stop()

    def action_reload_units(self) -> None:
        keep_id = self._state.focused_id or self._current_unit_id()
        rows = collect_unit_rows(self._root)
        self._state.reload_rows(rows)
        self._render_table(preferred_unit_id=keep_id)

    def action_toggle_row(self) -> None:
        if self.query_one("#search", Input).has_focus:
            return
        unit_id = self._current_unit_id()
        if not unit_id:
            return
        self._state.toggle_selected(unit_id)
        self._render_table(preferred_unit_id=unit_id)

    def action_select_visible(self) -> None:
        keep_id = self._state.focused_id or self._current_unit_id()
        self._state.select_visible()
        self._render_table(preferred_unit_id=keep_id)

    def action_unselect_visible(self) -> None:
        keep_id = self._state.focused_id or self._current_unit_id()
        self._state.unselect_visible()
        self._render_table(preferred_unit_id=keep_id)

    def _selected_ids(self) -> list[str]:
        return sorted(self._state.selected_ids)

    def action_backup_selected(self) -> None:
        selected = self._selected_ids()
        if not selected:
            self._render_status("no selected units")
            return
        success = 0
        failed = 0
        for unit_id in selected:
            code = self._capture_call(
                run_backup,
                self._root,
                self._protocol_registry,
                unit_id,
                False,
            )
            if code == 0:
                success += 1
            else:
                failed += 1
        self.action_reload_units()
        self._render_status(f"backup done: success={success} failed={failed}")

    def action_encrypt_selected(self) -> None:
        selected = self._selected_ids()
        if not selected:
            self._render_status("no selected units")
            return

        cfg = load_config(self._root)
        applied = 0
        skipped = 0
        for unit_id in selected:
            if unit_id in cfg.unit_encrypt:
                skipped += 1
                continue
            select_encrypt(self._root, unit_id)
            applied += 1
            cfg = load_config(self._root)
        self.action_reload_units()
        self._render_status(f"encrypt applied={applied} skipped={skipped}")

    def action_decrypt_selected(self) -> None:
        selected = self._selected_ids()
        if not selected:
            self._render_status("no selected units")
            return

        cfg = load_config(self._root)
        applied = 0
        skipped = 0
        for unit_id in selected:
            if unit_id in cfg.unit_decrypt:
                skipped += 1
                continue
            select_decrypt(self._root, unit_id)
            applied += 1
            cfg = load_config(self._root)
        self.action_reload_units()
        self._render_status(f"decrypt applied={applied} skipped={skipped}")

    async def action_remove_selected(self) -> None:
        selected = self._selected_ids()
        if not selected:
            self._render_status("no selected units")
            return

        confirm = await self.push_screen_wait(
            ConfirmScreen(
                "Remove selected units from active selection?\n\n" + "\n".join(selected)
            )
        )
        if not confirm:
            self._render_status("remove cancelled")
            return

        for unit_id in selected:
            select_remove(self._root, unit_id)
            self._state.selected_ids.discard(unit_id)
        self.action_reload_units()
        self._render_status(f"removed units={len(selected)}")

    async def action_add_manual(self) -> None:
        unit_id = await self.push_screen_wait(
            TextPromptScreen("Add Unit", "Unit id (e.g. github/owner/repo):")
        )
        if unit_id is None:
            self._render_status("add cancelled")
            return
        unit_id = unit_id.strip()
        if not unit_id:
            self._render_status("empty unit id")
            return

        select_add(self._root, unit_id)
        self.action_reload_units()
        self._state.selected_ids.add(unit_id)
        self._render_table(preferred_unit_id=unit_id)
        self._render_status(f"added unit={unit_id}")

    async def action_discover_add(self) -> None:
        protocol = "github"
        user = await self.push_screen_wait(
            TextPromptScreen(
                "Discover GitHub",
                "GitHub user/org (empty = infer from gh auth):",
                "",
            )
        )
        if user is None:
            self._render_status("discover cancelled")
            return

        limit_raw = await self.push_screen_wait(
            TextPromptScreen("Discover GitHub", "Max units:", "50")
        )
        if limit_raw is None:
            self._render_status("discover cancelled")
            return
        try:
            limit = int(limit_raw)
        except ValueError:
            self._render_status("invalid limit")
            return

        try:
            discovered = self._capture_call(
                discover_units,
                self._protocol_registry,
                protocol,
                user=user.strip() or None,
                limit=limit,
            )
        except Exception as exc:
            self._render_status(f"discover failed: {exc}")
            return

        candidates = [
            DiscoverCandidate(
                unit_id=item.unit_id,
                info=(
                    f"default_selected={item.default_selected} "
                    f"default_encrypt={item.default_encrypt} details={item.details}"
                ),
                default_selected=item.default_selected,
            )
            for item in discovered
        ]
        chosen = await self.push_screen_wait(DiscoverSelectScreen(candidates))
        if not chosen:
            self._render_status("discover add cancelled")
            return

        for unit_id in chosen:
            select_add(self._root, unit_id)
            self._state.selected_ids.add(unit_id)

        self.action_reload_units()
        self._render_status(f"discover added units={len(chosen)}")


def run_tui(root: Path) -> int:
    app = BackupTextualApp(root)
    app.run()
    return 0
