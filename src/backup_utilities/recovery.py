from __future__ import annotations

from pathlib import Path
import tempfile

from cryptography.exceptions import InvalidTag

from .crypto import decrypt_file, verify_passphrase_for_file
from .archive import extract_tar_zstd, sha256_file
from .crypto import encrypt_file
from .passphrase import clear_cached_passphrase, get_passphrase, prompt_new_passphrase
from .storage import (
    encrypted_payload_path,
    metadata_path,
    payload_rel_for_metadata,
    payload_path,
    read_json,
    resolve_payload_path,
    write_json_atomic,
)


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
    payload_path_value = resolve_payload_path(root, unit_id, payload_rel)
    if not payload_path_value.exists():
        raise FileNotFoundError(f"payload not found: {payload_path_value}")

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
            input_path=payload_path_value,
            output_path=out,
            passphrase=passphrase,
            aad_context=aad_context,
        )
    except (InvalidTag, ValueError):
        # Cached/env passphrase may be stale; require re-entry once.
        clear_cached_passphrase()
        retry_passphrase = prompt_new_passphrase("Backup passphrase (retry): ")
        decrypt_file(
            input_path=payload_path_value,
            output_path=out,
            passphrase=retry_passphrase,
            aad_context=aad_context,
        )
    print(f"decrypted to: {out}")
    return 0


def restore_unit_payload(root: Path, unit_id: str, out_dir: Path) -> Path:
    meta_path = metadata_path(root, unit_id)
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata not found: {meta_path}")

    meta = read_json(meta_path)
    payload_info = meta.get("payload", {})
    if not isinstance(payload_info, dict):
        raise ValueError(f"metadata payload missing: {unit_id}")

    payload_rel = str(payload_info.get("path", ""))
    if not payload_rel:
        raise ValueError(f"metadata payload.path missing: {unit_id}")

    payload_path_value = resolve_payload_path(root, unit_id, payload_rel)
    if not payload_path_value.exists():
        raise FileNotFoundError(f"payload not found: {payload_path_value}")

    out_dir.mkdir(parents=True, exist_ok=True)
    if bool(payload_info.get("encrypted", False)):
        _restore_encrypted_payload(
            payload_path_value=payload_path_value,
            payload_rel=payload_rel,
            unit_id=unit_id,
            snapshot_time=str(meta.get("snapshot_time", "")),
            out_dir=out_dir,
        )
    else:
        extract_tar_zstd(payload_path_value, out_dir)
    return out_dir


def _restore_encrypted_payload(
    *,
    payload_path_value: Path,
    payload_rel: str,
    unit_id: str,
    snapshot_time: str,
    out_dir: Path,
) -> None:
    aad_context = {
        "unit_id": unit_id,
        "snapshot_time": snapshot_time,
        "payload_name": Path(payload_rel).name,
    }

    with tempfile.TemporaryDirectory(prefix="backup-restore-") as tmp:
        decrypted_archive = Path(tmp) / "payload.tar.zst"
        passphrase = get_passphrase()
        try:
            decrypt_file(
                input_path=payload_path_value,
                output_path=decrypted_archive,
                passphrase=passphrase,
                aad_context=aad_context,
            )
        except (InvalidTag, ValueError):
            # Cached/env passphrase may be stale; require re-entry once.
            clear_cached_passphrase()
            retry_passphrase = prompt_new_passphrase("Backup passphrase (retry): ")
            decrypt_file(
                input_path=payload_path_value,
                output_path=decrypted_archive,
                passphrase=retry_passphrase,
                aad_context=aad_context,
            )
        extract_tar_zstd(decrypted_archive, out_dir)


def verify_unit_passphrase(root: Path, unit_id: str, passphrase: str) -> str:
    """Return verification note for one unit using current passphrase.

    Returns one of: "ok", "mismatch", "plain", "error".
    """
    meta_path = metadata_path(root, unit_id)
    if not meta_path.exists():
        return "error"

    meta = read_json(meta_path)
    payload_info = meta.get("payload", {})
    encrypted = bool(payload_info.get("encrypted", False))
    if not encrypted:
        return "plain"

    payload_rel = str(payload_info.get("path", ""))
    if not payload_rel:
        return "error"
    payload_path_value = resolve_payload_path(root, unit_id, payload_rel)
    if not payload_path_value.exists():
        return "error"

    aad_context = {
        "unit_id": unit_id,
        "snapshot_time": str(meta.get("snapshot_time", "")),
        "payload_name": Path(payload_rel).name,
    }

    try:
        verify_passphrase_for_file(
            input_path=payload_path_value,
            passphrase=passphrase,
            aad_context=aad_context,
        )
    except InvalidTag:
        return "mismatch"
    except Exception:
        return "error"
    return "ok"


def set_unit_payload_encryption(
    root: Path,
    unit_id: str,
    encrypt: bool,
    *,
    passphrase: str | None = None,
) -> str:
    """Set payload encryption state in-place for one unit.

    Returns:
    - "updated": payload rewritten and metadata updated.
    - "unchanged": payload already in target state.
    - "missing": metadata/payload unavailable.
    """
    meta_path = metadata_path(root, unit_id)
    if not meta_path.exists():
        return "missing"

    meta = read_json(meta_path)
    payload_info = meta.get("payload", {})
    if not isinstance(payload_info, dict):
        return "missing"

    current_encrypted = bool(payload_info.get("encrypted", False))
    payload_rel = str(payload_info.get("path", ""))
    if not payload_rel:
        return "missing"
    current_payload = resolve_payload_path(root, unit_id, payload_rel)
    if not current_payload.exists():
        return "missing"

    if current_encrypted == encrypt:
        return "unchanged"

    snapshot_time = str(meta.get("snapshot_time", ""))
    if encrypt:
        secret = passphrase or get_passphrase(confirm_new=True)
        final_payload = encrypted_payload_path(root, unit_id)
        tmp_payload = final_payload.with_name(f"{final_payload.name}.tmp")
        enc = encrypt_file(
            input_path=current_payload,
            output_path=tmp_payload,
            passphrase=secret,
            aad_context={
                "unit_id": unit_id,
                "snapshot_time": snapshot_time,
                "payload_name": final_payload.name,
            },
        )
        tmp_payload.replace(final_payload)
        payload_path(root, unit_id).unlink(missing_ok=True)
        meta["payload"] = {
            **payload_info,
            "path": payload_rel_for_metadata(root, unit_id, final_payload),
            "size_bytes": enc.size_bytes,
            "sha256": enc.sha256_hex,
            "encrypted": True,
        }
        meta["encryption"] = enc.encryption_metadata
    else:
        secret = passphrase or get_passphrase()
        final_payload = payload_path(root, unit_id)
        tmp_payload = final_payload.with_name(f"{final_payload.name}.tmp")
        decrypt_file(
            input_path=current_payload,
            output_path=tmp_payload,
            passphrase=secret,
            aad_context={
                "unit_id": unit_id,
                "snapshot_time": snapshot_time,
                "payload_name": Path(payload_rel).name,
            },
        )
        digest = sha256_file(tmp_payload)
        size_bytes = tmp_payload.stat().st_size
        tmp_payload.replace(final_payload)
        encrypted_payload_path(root, unit_id).unlink(missing_ok=True)
        meta["payload"] = {
            **payload_info,
            "path": payload_rel_for_metadata(root, unit_id, final_payload),
            "size_bytes": size_bytes,
            "sha256": digest,
            "encrypted": False,
        }
        meta.pop("encryption", None)

    write_json_atomic(meta_path, meta)
    return "updated"
