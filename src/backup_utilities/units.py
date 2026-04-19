from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .storage import read_json


@dataclass(slots=True)
class UnitRow:
    unit_id: str
    unit_label: str
    selected: bool
    excluded: bool
    encrypt_policy: str
    last_snapshot_time: str | None
    payload_size_bytes: int | None
    last_verify_time: str | None


def _discover_metadata_unit_ids(root: Path) -> set[str]:
    units_root = root / "units"
    if not units_root.exists():
        return set()

    out: set[str] = set()
    for meta_path in units_root.rglob("metadata.json"):
        rel = meta_path.parent.relative_to(units_root)
        out.add(rel.as_posix())
    return out


def collect_unit_rows(root: Path) -> list[UnitRow]:
    cfg = load_config(root)
    known_ids = (
        set(cfg.unit_include)
        | set(cfg.unit_exclude)
        | _discover_metadata_unit_ids(root)
    )

    rows: list[UnitRow] = []
    for unit_id in sorted(known_ids):
        meta_path = root / "units" / unit_id / "metadata.json"
        meta = read_json(meta_path) if meta_path.exists() else {}
        payload = meta.get("payload", {}) if isinstance(meta, dict) else {}
        verify = meta.get("verify", {}) if isinstance(meta, dict) else {}
        check = meta.get("check", {}) if isinstance(meta, dict) else {}
        protocol_meta = (
            meta.get("protocol_metadata", {}) if isinstance(meta, dict) else {}
        )

        if isinstance(payload, dict) and isinstance(payload.get("encrypted"), bool):
            policy_display = "encrypted" if bool(payload.get("encrypted")) else "plain"
        else:
            policy_display = "auto(initial)"

        unit_label = unit_id
        if unit_id.startswith("gdrive/folder/") and isinstance(protocol_meta, dict):
            folder_name = protocol_meta.get("folder_name")
            folder_id = protocol_meta.get("folder_id")
            if folder_name and folder_id:
                unit_label = f"gdrive/{folder_name} [{folder_id}]"

        rows.append(
            UnitRow(
                unit_id=unit_id,
                unit_label=unit_label,
                selected=unit_id in cfg.unit_include
                and unit_id not in cfg.unit_exclude,
                excluded=unit_id in cfg.unit_exclude,
                encrypt_policy=policy_display,
                last_snapshot_time=(
                    str(meta.get("snapshot_time"))
                    if meta.get("snapshot_time")
                    else None
                ),
                payload_size_bytes=(
                    int(payload.get("size_bytes"))
                    if isinstance(payload, dict)
                    and payload.get("size_bytes") is not None
                    else None
                ),
                last_verify_time=(
                    str(check.get("last_check_time"))
                    if isinstance(check, dict) and check.get("last_check_time")
                    else str(meta.get("snapshot_time"))
                    if meta.get("snapshot_time")
                    else str(verify.get("last_check_time"))
                    if isinstance(verify, dict) and verify.get("last_check_time")
                    else None
                ),
            )
        )

    return rows
