from __future__ import annotations

from pathlib import Path

from ..protocols import default_registry
from ..runner import run_backup
from ..selectors import select_decrypt, select_encrypt, select_remove
from .common import selected_units, unit_status_text
from .dialog import Whiptail


def _select_unit(w: Whiptail, root: Path) -> str | None:
    units = selected_units(root)
    if not units:
        w.msgbox("Backup Units", "No selected units. Use Add Units first.")
        return None

    options = [(u, "selected") for u in units]
    return w.menu("Backup Units", "Choose one unit", options)


def _unit_action_menu(w: Whiptail, unit_id: str) -> str | None:
    return w.menu(
        "Backup Units",
        f"Unit: {unit_id}",
        [
            ("status", "Show unit status"),
            ("encrypt", "Force encrypt"),
            ("decrypt", "Force decrypt"),
            ("remove", "Remove from selected units"),
            ("run", "Run backup for this unit"),
            ("back", "Back"),
        ],
    )


def run_backup_units_menu(w: Whiptail, root: Path) -> None:
    unit_id = _select_unit(w, root)
    if not unit_id:
        return

    while True:
        action = _unit_action_menu(w, unit_id)
        if action is None or action == "back":
            return

        if action == "status":
            w.msgbox("Unit Status", unit_status_text(root, unit_id))
        elif action == "encrypt":
            select_encrypt(root, unit_id)
            w.msgbox("Done", f"force encrypt: {unit_id}")
        elif action == "decrypt":
            select_decrypt(root, unit_id)
            w.msgbox("Done", f"force decrypt: {unit_id}")
        elif action == "remove":
            if w.yesno("Confirm Remove", f"Remove selected unit?\n\n{unit_id}"):
                select_remove(root, unit_id)
                w.msgbox("Done", f"excluded: {unit_id}")
                return
        elif action == "run":
            dry_run = w.yesno("Run Backup", "Run in dry-run mode?")
            code = run_backup(root, default_registry(), unit=unit_id, dry_run=dry_run)
            w.msgbox("Run Result", f"run finished with code: {code}")
