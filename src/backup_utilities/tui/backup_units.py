from __future__ import annotations

from pathlib import Path
import tempfile

from ..config import load_config
from ..protocols import default_registry
from ..runner import run_backup
from ..selectors import select_decrypt, select_encrypt, select_remove
from .common import selected_units, unit_status_text
from .dialog import Whiptail


def _pick_units(w: Whiptail, root: Path) -> list[str] | None:
    units = selected_units(root)
    if not units:
        w.msgbox("Backup Units", "No selected units. Use Add Units first.")
        return None

    options = [(unit_id, "selected", False) for unit_id in units]
    return w.checklist(
        "Backup Units",
        "Select units (space to toggle)",
        options,
    )


def _action_menu(w: Whiptail, count: int) -> str | None:
    return w.menu(
        "Backup Units",
        f"Selected units: {count}",
        [
            ("status", "Show unit status"),
            ("run", "Run backup for selected units"),
            ("encrypt", "Force encrypt (skip already encrypted)"),
            ("decrypt", "Force decrypt"),
            ("remove", "Remove from selected units"),
            ("back", "Back"),
        ],
    )


def _show_status(w: Whiptail, root: Path, unit_ids: list[str]) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as tmp:
        for idx, unit_id in enumerate(unit_ids, start=1):
            if idx > 1:
                tmp.write("\n")
                tmp.write("-" * 80)
                tmp.write("\n")
            tmp.write(unit_status_text(root, unit_id))
            tmp.write("\n")
        tmp_path = Path(tmp.name)

    try:
        w.textbox("Unit Status", tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _bulk_encrypt(root: Path, unit_ids: list[str]) -> tuple[int, int]:
    cfg = load_config(root)
    applied = 0
    skipped = 0
    for unit_id in unit_ids:
        if unit_id in cfg.unit_encrypt:
            skipped += 1
            continue
        select_encrypt(root, unit_id)
        applied += 1
    return applied, skipped


def _bulk_decrypt(root: Path, unit_ids: list[str]) -> tuple[int, int]:
    cfg = load_config(root)
    applied = 0
    skipped = 0
    for unit_id in unit_ids:
        if unit_id in cfg.unit_decrypt:
            skipped += 1
            continue
        select_decrypt(root, unit_id)
        applied += 1
    return applied, skipped


def _bulk_remove(root: Path, unit_ids: list[str]) -> int:
    removed = 0
    for unit_id in unit_ids:
        select_remove(root, unit_id)
        removed += 1
    return removed


def _bulk_run_backup(w: Whiptail, root: Path, unit_ids: list[str]) -> None:
    dry_run = w.yesno("Run Backup", "Run in dry-run mode?")
    success = 0
    failed = 0

    for unit_id in unit_ids:
        code = run_backup(root, default_registry(), unit=unit_id, dry_run=dry_run)
        if code == 0:
            success += 1
        else:
            failed += 1

    w.msgbox(
        "Run Result",
        "\n".join(
            [
                f"selected units: {len(unit_ids)}",
                f"success units: {success}",
                f"failed units: {failed}",
            ]
        ),
    )


def run_backup_units_menu(w: Whiptail, root: Path) -> None:
    picked = _pick_units(w, root)
    if not picked:
        return

    while True:
        action = _action_menu(w, len(picked))
        if action is None or action == "back":
            return

        if action == "status":
            _show_status(w, root, picked)
        elif action == "run":
            _bulk_run_backup(w, root, picked)
        elif action == "encrypt":
            applied, skipped = _bulk_encrypt(root, picked)
            w.msgbox("Done", f"force encrypt applied: {applied}\nskipped: {skipped}")
        elif action == "decrypt":
            applied, skipped = _bulk_decrypt(root, picked)
            w.msgbox("Done", f"force decrypt applied: {applied}\nskipped: {skipped}")
        elif action == "remove":
            if w.yesno(
                "Confirm Remove",
                "Remove selected units?\n\n" + "\n".join(picked),
            ):
                removed = _bulk_remove(root, picked)
                w.msgbox("Done", f"excluded units: {removed}")
                return
