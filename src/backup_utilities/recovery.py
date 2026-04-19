from __future__ import annotations

from pathlib import Path

from cryptography.exceptions import InvalidTag

from .crypto import decrypt_file
from .passphrase import clear_cached_passphrase, get_passphrase, prompt_new_passphrase
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

    aad_context = {
        "unit_id": unit_id,
        "snapshot_time": str(meta.get("snapshot_time", "")),
        "payload_name": Path(payload_rel).name,
    }

    passphrase = get_passphrase()
    try:
        decrypt_file(
            input_path=payload_path,
            output_path=out,
            passphrase=passphrase,
            aad_context=aad_context,
        )
    except (InvalidTag, ValueError):
        # Cached/env passphrase may be stale; require re-entry once.
        clear_cached_passphrase()
        retry_passphrase = prompt_new_passphrase("Backup passphrase (retry): ")
        decrypt_file(
            input_path=payload_path,
            output_path=out,
            passphrase=retry_passphrase,
            aad_context=aad_context,
        )
    print(f"decrypted to: {out}")
    return 0
