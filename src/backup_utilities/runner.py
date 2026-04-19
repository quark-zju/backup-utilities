from __future__ import annotations

from pathlib import Path
import tempfile

from .archive import create_tar_zstd, sha256_file
from .config import Config, load_config
from .crypto import encrypt_file
from .layout import load_index
from .logging_utils import append_log
from .passphrase import get_passphrase
from .protocols import ProtocolRegistry
from .storage import (
    encrypted_payload_path,
    metadata_path,
    now_utc,
    payload_path,
    read_json,
    unit_dir,
    write_json_atomic,
)


def _selected_units(root: Path, unit_arg: str | None) -> list[str]:
    cfg = load_config(root)
    units = [unit for unit in cfg.unit_include if unit not in cfg.unit_exclude]
    if unit_arg:
        if unit_arg not in units:
            raise ValueError(f"unit not selected: {unit_arg}")
        return [unit_arg]
    return units


def _should_encrypt(
    *,
    unit_id: str,
    cfg: Config,
    protocol,
    protocol_metadata: dict[str, object],
) -> bool:
    if unit_id in cfg.unit_encrypt:
        return True
    if unit_id in cfg.unit_decrypt:
        return False

    protocol_default = protocol.should_encrypt_auto(
        protocol_metadata=protocol_metadata,
        cfg=cfg,
    )
    if protocol_default is not None:
        return protocol_default
    return cfg.default_encrypt


def run_backup(
    root: Path, registry: ProtocolRegistry, unit: str | None, dry_run: bool
) -> int:
    cfg = load_config(root)
    units = _selected_units(root, unit)
    if not units:
        print("no selected units")
        return 0

    index = load_index(root)
    changed = 0
    failed = 0

    for unit_id in units:
        protocol = registry.protocol_for_unit(unit_id)
        unit_meta_path = metadata_path(root, unit_id)
        prev = read_json(unit_meta_path) if unit_meta_path.exists() else None
        check_time = now_utc()

        try:
            fingerprint = protocol.compute_fingerprint(unit_id)
        except Exception as exc:
            print(f"failed fingerprint: {unit_id}: {exc}")
            append_log(root, "runner", f"fingerprint failed unit={unit_id} error={exc}")
            failed += 1
            continue
        prev_fp = str(prev.get("source_fingerprint")) if prev else None
        append_log(
            root,
            "runner",
            (
                f"fingerprint check unit={unit_id} "
                f"prev={prev_fp or '-'} current={fingerprint.fingerprint}"
            ),
        )

        if prev_fp == fingerprint.fingerprint:
            print(f"skip unchanged: {unit_id}")
            append_log(root, "runner", f"decision skip unit={unit_id} reason=match")
            if prev is not None:
                prev["check"] = {
                    "last_check_time": check_time,
                    "status": "unchanged",
                }
                write_json_atomic(unit_meta_path, prev)
            continue

        changed += 1
        print(f"backup: {unit_id}")
        append_log(
            root,
            "runner",
            f"decision backup unit={unit_id} reason=mismatch_or_first_snapshot",
        )
        if dry_run:
            append_log(root, "runner", f"dry-run skip-write unit={unit_id}")
            continue

        archive_tmp: Path | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="backup-unit-") as tmp:
                staging = Path(tmp)
                exported = protocol.export_snapshot(unit_id, staging)
                target_dir = unit_dir(root, unit_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                snapshot_time = now_utc()

                archive_tmp = target_dir / "payload.tar.zst.tmp"
                create_tar_zstd(exported.source_path, archive_tmp)

                encrypt = _should_encrypt(
                    unit_id=unit_id,
                    cfg=cfg,
                    protocol=protocol,
                    protocol_metadata=fingerprint.protocol_metadata,
                )
                append_log(
                    root, "runner", f"payload encrypt unit={unit_id} value={encrypt}"
                )

                encryption_metadata: dict[str, object] | None = None
                if encrypt:
                    final_payload = encrypted_payload_path(root, unit_id)
                    encrypted_tmp = final_payload.with_name(f"{final_payload.name}.tmp")
                    enc = encrypt_file(
                        input_path=archive_tmp,
                        output_path=encrypted_tmp,
                        passphrase=get_passphrase(confirm_new=True),
                        aad_context={
                            "unit_id": unit_id,
                            "snapshot_time": snapshot_time,
                            "payload_name": final_payload.name,
                        },
                    )
                    archive_tmp.unlink(missing_ok=True)
                    digest = enc.sha256_hex
                    size_bytes = enc.size_bytes
                    encryption_metadata = enc.encryption_metadata
                    encrypted_tmp.replace(final_payload)
                    payload_path(root, unit_id).unlink(missing_ok=True)
                else:
                    final_payload = payload_path(root, unit_id)
                    digest = sha256_file(archive_tmp)
                    size_bytes = archive_tmp.stat().st_size
                    archive_tmp.replace(final_payload)
                    encrypted_payload_path(root, unit_id).unlink(missing_ok=True)

                metadata = {
                    "unit_id": unit_id,
                    "protocol": protocol.name,
                    "snapshot_time": snapshot_time,
                    "check": {
                        "last_check_time": check_time,
                        "status": "updated",
                    },
                    "source_fingerprint": fingerprint.fingerprint,
                    "payload": {
                        "path": str(final_payload.relative_to(root)),
                        "size_bytes": size_bytes,
                        "sha256": digest,
                        "compressed": "zstd",
                        "encrypted": encrypt,
                    },
                    "protocol_metadata": fingerprint.protocol_metadata,
                    "tool_version": "0.1.0",
                }
                if encryption_metadata is not None:
                    metadata["encryption"] = encryption_metadata
                write_json_atomic(unit_meta_path, metadata)
                append_log(root, "runner", f"metadata updated unit={unit_id}")

                index[unit_id] = {
                    "snapshot_time": metadata["snapshot_time"],
                    "source_fingerprint": metadata["source_fingerprint"],
                    "payload_sha256": digest,
                    "payload_size_bytes": size_bytes,
                }
        except Exception as exc:
            if archive_tmp is not None:
                archive_tmp.unlink(missing_ok=True)
            print(f"failed backup: {unit_id}: {exc}")
            append_log(root, "runner", f"backup failed unit={unit_id} error={exc}")
            failed += 1
            continue

    write_json_atomic(root / "state" / "index.json", index)
    append_log(root, "runner", f"backup summary changed={changed} failed={failed}")
    print(f"done. changed units: {changed}, failed units: {failed}")
    return 1 if failed else 0


def verify_units(root: Path, unit: str | None) -> int:
    units = _selected_units(root, unit)
    if not units:
        print("no selected units")
        return 0

    ok = 0
    failed = 0
    for unit_id in units:
        meta_path = metadata_path(root, unit_id)
        if not meta_path.exists():
            print(f"missing files: {unit_id}")
            failed += 1
            continue

        meta = read_json(meta_path)
        check_time = now_utc()
        payload_rel = meta["payload"]["path"]
        payload = root / str(payload_rel)
        if not payload.exists():
            print(f"missing payload: {unit_id}")
            meta["verify"] = {
                "last_check_time": check_time,
                "ok": False,
                "reason": "missing payload",
            }
            write_json_atomic(meta_path, meta)
            failed += 1
            continue
        expected = str(meta["payload"]["sha256"])
        current = sha256_file(payload)
        if expected == current:
            print(f"ok: {unit_id}")
            meta["verify"] = {
                "last_check_time": check_time,
                "ok": True,
            }
            write_json_atomic(meta_path, meta)
            ok += 1
        else:
            print(f"mismatch: {unit_id}")
            meta["verify"] = {
                "last_check_time": check_time,
                "ok": False,
                "reason": "sha256 mismatch",
            }
            write_json_atomic(meta_path, meta)
            failed += 1

    print(f"verify done. ok={ok} failed={failed}")
    return 1 if failed else 0
