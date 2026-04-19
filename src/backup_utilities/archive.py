from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess


def create_tar_zstd(source_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "tar",
        "--zstd",
        "-cf",
        str(output_path),
        "-C",
        str(source_path.parent),
        source_path.name,
    ]
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"tar failed: {res.stderr.strip()}")


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
