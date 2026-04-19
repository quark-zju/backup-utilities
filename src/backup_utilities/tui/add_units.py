from __future__ import annotations

from pathlib import Path

from ..discovery import discover_units
from ..protocols import default_registry
from ..selectors import select_add
from .common import selected_units
from .dialog import Whiptail


def _discover_params(w: Whiptail, protocol: str) -> tuple[str | None, int] | None:
    user: str | None = None
    if protocol == "github":
        user_raw = w.inputbox(
            "Discover GitHub",
            "GitHub user/org (empty = infer from gh auth):",
            "",
        )
        if user_raw is None:
            return None
        user = user_raw if user_raw else None

    limit_raw = w.inputbox("Discover", "Max units:", "50")
    if not limit_raw:
        return None
    return user, int(limit_raw)


def _discover_and_add(w: Whiptail, root: Path) -> None:
    registry = default_registry()
    protocol = w.menu(
        "Add Units",
        "Choose protocol",
        [(name, f"Discover {name} units") for name in registry.protocol_names()],
    )
    if not protocol:
        return

    params = _discover_params(w, protocol)
    if not params:
        return
    user, limit = params

    units = discover_units(registry, protocol, user=user, limit=limit)
    already = set(selected_units(root))

    checklist_options: list[tuple[str, str, bool]] = []
    for item in units:
        desc = (
            f"default_selected={item.default_selected} "
            f"default_encrypt={item.default_encrypt} details={item.details}"
        )
        enabled = item.default_selected and item.unit_id not in already
        checklist_options.append((item.unit_id, desc, enabled))

    if not checklist_options:
        w.msgbox("Discover", "No units found.")
        return

    picked = w.checklist(
        "Discover Result",
        "Select units to add (space to toggle)",
        checklist_options,
    )
    if picked is None:
        return

    for unit_id in picked:
        select_add(root, unit_id)

    w.msgbox("Done", f"added units: {len(picked)}")


def _add_manually(w: Whiptail, root: Path) -> None:
    unit_id = w.inputbox("Add Unit", "Unit id (e.g. github/owner/repo):")
    if not unit_id:
        return
    select_add(root, unit_id)
    w.msgbox("Done", f"selected: {unit_id}")


def run_add_units_menu(w: Whiptail, root: Path) -> None:
    while True:
        action = w.menu(
            "Add Units",
            "Choose add method",
            [
                ("discover", "Add by discover (batch checklist)"),
                ("manual", "Add manually"),
                ("back", "Back"),
            ],
        )

        if action is None or action == "back":
            return
        if action == "discover":
            _discover_and_add(w, root)
        elif action == "manual":
            _add_manually(w, root)
