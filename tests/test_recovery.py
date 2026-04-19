from __future__ import annotations

import json
from pathlib import Path

from backup_utilities.recovery import restore_unit_payload


def test_restore_unit_payload_plain_archive_skips_passphrase_prompt(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path
    unit_id = "github/quark/demo"
    unit_dir = root / "units" / "github" / "quark" / "demo"
    unit_dir.mkdir(parents=True)

    metadata = {
        "unit_id": unit_id,
        "snapshot_time": "2026-04-19T00:00:00+00:00",
        "payload": {
            "path": "payload.tar.zst",
            "encrypted": False,
        },
    }
    (unit_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=True),
        encoding="utf-8",
    )
    payload = unit_dir / "payload.tar.zst"
    payload.write_bytes(b"archive-bytes")

    extracted: list[tuple[Path, Path]] = []

    def fake_extract(archive_path: Path, output_dir: Path) -> None:
        extracted.append((archive_path, output_dir))

    def fail_get_passphrase(*args, **kwargs) -> str:
        raise AssertionError("passphrase prompt should not run for plain payload")

    monkeypatch.setattr("backup_utilities.recovery.extract_tar_zstd", fake_extract)
    monkeypatch.setattr("backup_utilities.recovery.get_passphrase", fail_get_passphrase)

    out_dir = root / "restore"
    restored = restore_unit_payload(root, unit_id, out_dir)

    assert restored == out_dir
    assert extracted == [(payload, out_dir)]
