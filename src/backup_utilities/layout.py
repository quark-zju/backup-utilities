from __future__ import annotations

from pathlib import Path
import json

from .config import default_config, write_config


def init_root(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "units").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    cfg_path = root / "config" / "backup_config.toml"
    if not cfg_path.exists():
        write_config(root, default_config())

    index_path = root / "state" / "index.json"
    if not index_path.exists():
        index_path.write_text("{}\n", encoding="utf-8")


def load_index(root: Path) -> dict[str, dict[str, object]]:
    path = root / "state" / "index.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
