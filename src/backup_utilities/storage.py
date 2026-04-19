from __future__ import annotations

from datetime import datetime, UTC
import json
from pathlib import Path


def unit_dir(root: Path, unit_id: str) -> Path:
    return root / "units" / Path(unit_id)


def metadata_path(root: Path, unit_id: str) -> Path:
    return unit_dir(root, unit_id) / "metadata.json"


def payload_path(root: Path, unit_id: str) -> Path:
    return unit_dir(root, unit_id) / "payload.tar.zst"


def encrypted_payload_path(root: Path, unit_id: str) -> Path:
    return unit_dir(root, unit_id) / "payload.tar.zst.enc"


def resolve_payload_path(root: Path, unit_id: str, payload_rel: str) -> Path:
    rel = Path(payload_rel)
    if rel.is_absolute():
        return rel
    # New format: relative to unit directory.
    unit_based = unit_dir(root, unit_id) / rel
    if unit_based.exists():
        return unit_based
    # Backward compatibility: older metadata used root-relative payload path.
    return root / rel


def payload_rel_for_metadata(root: Path, unit_id: str, payload_abs: Path) -> str:
    return str(payload_abs.relative_to(unit_dir(root, unit_id)))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp_path.replace(path)


def now_utc() -> str:
    return datetime.now(UTC).isoformat()
