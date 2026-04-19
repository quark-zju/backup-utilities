from __future__ import annotations

from pathlib import Path

from .add_units import run_add_units_menu
from .backup_units import run_backup_units_menu
from .common import global_status_text
from .dialog import Whiptail


def run_tui(root: Path) -> int:
    w = Whiptail()

    while True:
        choice = w.menu(
            "Backup TUI",
            "Select action",
            [
                ("backup_units", "Backup units"),
                ("add_units", "Add units"),
                ("status", "Global status"),
                ("exit", "Exit TUI"),
            ],
        )

        if choice is None or choice == "exit":
            return 0

        try:
            if choice == "backup_units":
                run_backup_units_menu(w, root)
            elif choice == "add_units":
                run_add_units_menu(w, root)
            elif choice == "status":
                w.msgbox("Status", global_status_text(root))
        except Exception as exc:
            w.msgbox("Error", str(exc))
