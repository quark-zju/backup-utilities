from __future__ import annotations

from pathlib import Path

from .crypto import decrypt_file, resolve_passphrase
from .storage import metadata_path, read_json


def decrypt_unit_payload(root: Path, unit_id: str, out: Path) -> int:
    meta_path = metadata_path(root, unit_id)
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata not found: {meta_path}")

    meta = read_json(meta_path)
    payload_info = meta.get("payload", {})
    encrypted = bool(payload_info.get("encrypted", False))
    if not encrypted:
        raise ValueError(f"unit payload is not encrypted: {unit_id}")

    payload_rel = str(payload_info.get("path", ""))
    if not payload_rel:
        raise ValueError(f"metadata payload.path missing: {unit_id}")
    payload_path = root / payload_rel
    if not payload_path.exists():
        raise FileNotFoundError(f"payload not found: {payload_path}")

    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    passphrase = resolve_passphrase()
    decrypt_file(
        input_path=payload_path,
        output_path=out,
        passphrase=passphrase,
        aad_context={
            "unit_id": unit_id,
            "snapshot_time": str(meta.get("snapshot_time", "")),
            "payload_name": Path(payload_rel).name,
        },
    )
    print(f"decrypted to: {out}")
    return 0
