from __future__ import annotations

from pathlib import Path

from ..config import load_config
from ..layout import load_index
from ..storage import metadata_path, read_json


def global_status_text(root: Path) -> str:
    cfg = load_config(root)
    index = load_index(root)
    lines = [
        f"root: {root}",
        f"selected units: {len(cfg.unit_include)}",
        f"excluded units: {len(cfg.unit_exclude)}",
        f"forced encrypt units: {len(cfg.unit_encrypt)}",
        f"forced decrypt units: {len(cfg.unit_decrypt)}",
        f"indexed snapshots: {len(index)}",
    ]
    return "\n".join(lines)


def selected_units(root: Path) -> list[str]:
    cfg = load_config(root)
    return [unit for unit in cfg.unit_include if unit not in cfg.unit_exclude]


def unit_status_text(root: Path, unit_id: str) -> str:
    cfg = load_config(root)
    meta_path = metadata_path(root, unit_id)

    encrypt_state = "auto"
    if unit_id in cfg.unit_encrypt:
        encrypt_state = "forced-encrypt"
    elif unit_id in cfg.unit_decrypt:
        encrypt_state = "forced-decrypt"

    lines = [
        f"unit: {unit_id}",
        f"selected: {unit_id in cfg.unit_include}",
        f"excluded: {unit_id in cfg.unit_exclude}",
        f"encrypt policy: {encrypt_state}",
        f"metadata exists: {meta_path.exists()}",
    ]

    if meta_path.exists():
        meta = read_json(meta_path)
        lines.extend(
            [
                f"last snapshot: {meta.get('snapshot_time', '')}",
                f"last fingerprint: {meta.get('source_fingerprint', '')}",
                f"payload: {meta.get('payload', {}).get('path', '')}",
            ]
        )

    return "\n".join(lines)
