from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import queue
import sys
import threading
import traceback

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

from ..config import load_config
from ..discovery import discover_units
from ..logging_utils import append_log
from ..passphrase import (
    clear_cached_passphrase,
    get_passphrase,
    has_passphrase_cached,
    set_cached_passphrase,
    validate_new_passphrase,
)
from ..protocols import default_registry
from ..runner import run_backup
from ..selectors import (
    select_add,
    select_decrypt,
    select_encrypt,
    select_exclude,
    select_remove,
    select_unexclude,
)
from ..units import collect_unit_rows
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


def _fmt_snapshot_date(value: str | None) -> str:
    if not value:
        return "-"
    # ISO-like value, keep only Y-m-d for snapshot column readability.
    return value.split("T", maxsplit=1)[0]


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
        Binding("/", "focus_search", "Search"),
        Binding("tab", "toggle_focus", "Focus"),
        Binding("ctrl+e", "manage_passphrase", "Passphrase"),
        Binding("space", "toggle_row", "Toggle"),
        Binding("a", "select_visible", "Select Visible"),
        Binding("n", "unselect_visible", "Unselect Visible"),
        Binding("b", "backup_selected", "Backup"),
        Binding("e", "encrypt_selected", "Encrypt"),
        Binding("d", "decrypt_selected", "Decrypt"),
        Binding("v", "toggle_exclude_selected", "Toggle Exclude"),
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
        self._backup_queue: queue.Queue[str | None] = queue.Queue()
        self._backup_events: queue.Queue[tuple[str, str, bool | None, str | None]] = (
            queue.Queue()
        )
        self._backup_status: dict[str, str] = {}
        self._backup_worker_stop = threading.Event()
        self._backup_worker = threading.Thread(
            target=self._backup_worker_main,
            name="backup-worker",
            daemon=True,
        )

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

    def _log(self, message: str) -> None:
        append_log(self._root, "tui", message)

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
        self.set_interval(0.2, self._drain_backup_events)
        self._backup_worker.start()
        self.action_reload_units()
        table.focus()
        self._log("START tui")

    def on_unmount(self) -> None:
        self._backup_worker_stop.set()
        self._backup_queue.put(None)
        self._log("STOP tui")

    def _capture_call(self, fn, *args, **kwargs):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return fn(*args, **kwargs)

    def _capture_call_with_output(self, fn, *args, **kwargs):
        out_io = StringIO()
        err_io = StringIO()
        with redirect_stdout(out_io), redirect_stderr(err_io):
            result = fn(*args, **kwargs)
        return result, out_io.getvalue(), err_io.getvalue()

    def _render_table(self, preferred_unit_id: str | None = None) -> None:
        if preferred_unit_id is None:
            preferred_unit_id = self._state.focused_id or self._current_unit_id()
        self._state.focused_id = preferred_unit_id

        table = self.query_one("#units_table", DataTable)
        table.clear(columns=False)
        for unit_id in self._state.visible_ids:
            row = self._state.all_rows[unit_id]
            marker = "x" if unit_id in self._state.selected_ids else ""
            runtime_status = self._backup_status.get(unit_id)
            unit_label = row.unit_id
            if row.excluded:
                unit_label = f"{unit_label} [excluded]"
            if runtime_status == "queued":
                unit_label = f"{unit_label} (queued)"
            elif runtime_status == "backing_up":
                unit_label = f"{unit_label} (backing up)"
            table.add_row(
                marker,
                unit_label,
                row.encrypt_policy,
                _fmt_snapshot_date(row.last_snapshot_time),
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
        queued = len([x for x in self._backup_status.values() if x == "queued"])
        backing_up = len([x for x in self._backup_status.values() if x == "backing_up"])

        chunks = [
            (
                f"total={total} visible={visible} selected={selected} "
                f"hidden_selected={hidden} queued={queued} backing_up={backing_up}"
            )
        ]
        if self._state.query_error:
            chunks.append(f"query_error={self._state.query_error}")
        if message:
            chunks.append(message)
        status.update(" | ".join(chunks))

    def _backup_worker_main(self) -> None:
        while not self._backup_worker_stop.is_set():
            unit_id = self._backup_queue.get()
            if unit_id is None:
                break
            self._backup_events.put(("start", unit_id, None, None))
            self._log(f"backup start unit={unit_id}")
            result, out, err = self._capture_call_with_output(
                run_backup,
                self._root,
                self._protocol_registry,
                unit_id,
                False,
            )
            code = int(result)
            failure_message = None
            if code != 0:
                failure_message = self._extract_failure_message(out, err)
            self._backup_events.put(("done", unit_id, code == 0, failure_message))
            if code == 0:
                self._log(f"backup done unit={unit_id}")
            else:
                self._log(f"backup failed unit={unit_id} reason={failure_message}")

    @staticmethod
    def _extract_failure_message(stdout_text: str, stderr_text: str) -> str:
        merged_lines = [
            line.strip() for line in (stderr_text + "\n" + stdout_text).splitlines()
        ]
        merged_lines = [line for line in merged_lines if line]
        if not merged_lines:
            return "unknown failure"
        for line in reversed(merged_lines):
            if line.startswith("failed backup:"):
                return line
        for line in reversed(merged_lines):
            low = line.lower()
            if line.startswith("done. changed units:"):
                continue
            if "failed" in low or "error" in low or "mismatch" in low:
                return line
        return merged_lines[-1]

    def _drain_backup_events(self) -> None:
        updated = False
        message: str | None = None
        while True:
            try:
                phase, unit_id, ok, detail = self._backup_events.get_nowait()
            except queue.Empty:
                break

            updated = True
            if phase == "start":
                self._backup_status[unit_id] = "backing_up"
                message = f"backing up: {unit_id}"
            elif phase == "done":
                self._backup_status.pop(unit_id, None)
                if ok:
                    message = f"backup done: {unit_id}"
                else:
                    if detail:
                        message = f"backup failed: {unit_id}: {detail}"
                    else:
                        message = f"backup failed: {unit_id}"

        if updated:
            self.action_reload_units()
            self._render_status(message)

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

    def action_manage_passphrase(self) -> None:
        self.run_worker(self._manage_passphrase_flow(), thread=False, exclusive=True)

    async def _manage_passphrase_flow(self) -> None:
        if has_passphrase_cached():
            clear_cached_passphrase()
            self._render_status("passphrase cache cleared")
            self._log("passphrase cache cleared")
            return

        entered = await self._prompt_new_passphrase_with_confirmation(
            title="Passphrase",
            first_prompt="Enter passphrase to cache in memory:",
        )
        if entered is None:
            self._render_status("passphrase unchanged")
            return
        set_cached_passphrase(entered)
        self._render_status("passphrase cached")
        self._log("passphrase cached")

    async def _prompt_new_passphrase_with_confirmation(
        self,
        *,
        title: str,
        first_prompt: str,
    ) -> str | None:
        first = await self.push_screen_wait(
            TextPromptScreen(title, first_prompt, "", password=True)
        )
        if first is None:
            return None
        second = await self.push_screen_wait(
            TextPromptScreen(title, "Confirm passphrase:", "", password=True)
        )
        if second is None:
            return None
        try:
            return validate_new_passphrase(
                first.strip(),
                second.strip(),
                require_confirmation=True,
            )
        except ValueError as exc:
            self._render_status(str(exc))
            return None

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
        self._update_selection_cell(unit_id)
        self._render_status()

    def _update_selection_cell(self, unit_id: str) -> None:
        if unit_id not in self._state.visible_ids:
            return
        row_index = self._state.visible_ids.index(unit_id)
        marker = "x" if unit_id in self._state.selected_ids else ""
        table = self.query_one("#units_table", DataTable)
        table.update_cell_at(Coordinate(row_index, 0), marker)

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

    def _operation_target_ids(self) -> list[str]:
        selected = self._selected_ids()
        if selected:
            return selected
        current = self._current_unit_id()
        if current:
            return [current]
        return []

    def _selected_need_passphrase(self, selected: list[str]) -> bool:
        cfg = load_config(self._root)
        if cfg.default_encrypt:
            return True
        for unit_id in selected:
            row = self._state.all_rows.get(unit_id)
            if row is None:
                continue
            if row.encrypt_policy != "forced-decrypt":
                return True
        return False

    def action_backup_selected(self) -> None:
        self.run_worker(self._backup_selected_flow(), thread=False, exclusive=True)

    async def _backup_selected_flow(self) -> None:
        selected = self._operation_target_ids()
        if not selected:
            self._render_status("no selected/focused units")
            return

        if self._selected_need_passphrase(selected):
            try:
                # Use env or cached value if already available.
                get_passphrase(allow_prompt=False)
            except Exception:
                entered = await self._prompt_new_passphrase_with_confirmation(
                    title="Backup Passphrase",
                    first_prompt="Passphrase required for encrypted backup:",
                )
                if entered is None:
                    self._render_status("backup cancelled: passphrase not provided")
                    return
                set_cached_passphrase(entered)

        queued_now = 0
        skipped = 0
        for unit_id in selected:
            current = self._backup_status.get(unit_id)
            if current in {"queued", "backing_up"}:
                skipped += 1
                continue
            self._backup_status[unit_id] = "queued"
            self._backup_queue.put(unit_id)
            queued_now += 1
        self._log(f"backup queued count={queued_now} skipped={skipped}")
        self._state.selected_ids.clear()
        self._render_table()
        self._render_status(f"backup queued={queued_now} skipped={skipped}")

    def action_encrypt_selected(self) -> None:
        selected = self._operation_target_ids()
        if not selected:
            self._render_status("no selected/focused units")
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
        self._state.selected_ids.clear()
        self.action_reload_units()
        self._render_status(f"encrypt applied={applied} skipped={skipped}")
        self._log(f"encrypt applied={applied} skipped={skipped}")

    def action_decrypt_selected(self) -> None:
        selected = self._operation_target_ids()
        if not selected:
            self._render_status("no selected/focused units")
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
        self._state.selected_ids.clear()
        self.action_reload_units()
        self._render_status(f"decrypt applied={applied} skipped={skipped}")
        self._log(f"decrypt applied={applied} skipped={skipped}")

    def action_remove_selected(self) -> None:
        self.run_worker(self._remove_selected_flow(), thread=False, exclusive=True)

    async def _remove_selected_flow(self) -> None:
        selected = self._operation_target_ids()
        if not selected:
            self._render_status("no selected/focused units")
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
        self._state.selected_ids.clear()
        self.action_reload_units()
        self._render_status(f"removed units={len(selected)}")
        self._log(f"removed units={len(selected)}")

    def action_toggle_exclude_selected(self) -> None:
        selected = self._operation_target_ids()
        if not selected:
            self._render_status("no selected/focused units")
            return

        excluded_now = 0
        unexcluded_now = 0
        cfg = load_config(self._root)
        excluded = set(cfg.unit_exclude)
        for unit_id in selected:
            if unit_id in excluded:
                select_unexclude(self._root, unit_id)
                unexcluded_now += 1
                excluded.remove(unit_id)
            else:
                select_exclude(self._root, unit_id)
                excluded_now += 1
                excluded.add(unit_id)

        self._state.selected_ids.clear()
        self.action_reload_units()
        self._render_status(
            f"exclude toggled: excluded={excluded_now} unexcluded={unexcluded_now}"
        )
        self._log(f"exclude toggled excluded={excluded_now} unexcluded={unexcluded_now}")

    def action_add_manual(self) -> None:
        self.run_worker(self._add_manual_flow(), thread=False, exclusive=True)

    async def _add_manual_flow(self) -> None:
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
        self._log(f"added unit={unit_id}")

    def action_discover_add(self) -> None:
        self.run_worker(self._discover_add_flow(), thread=False, exclusive=True)

    async def _discover_add_flow(self) -> None:
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
        self._log(f"discover add units={len(chosen)}")


def run_tui(root: Path) -> int:
    app = BackupTextualApp(root)
    app.run()
    return 0
