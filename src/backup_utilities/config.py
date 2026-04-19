from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
import uuid as _uuid

CONFIG_REL_PATH = Path("config") / "backup_config.toml"


@dataclass(slots=True)
class Config:
    uuid: str = ""
    compression_level: int = 10
    max_workers: int = 1
    default_encrypt: bool = False
    github_include_forks: bool = False
    github_include_private: bool = True
    github_default_private_encrypt: bool = True
    unit_include: list[str] = field(default_factory=list)
    unit_exclude: list[str] = field(default_factory=list)


def config_path(root: Path) -> Path:
    return root / CONFIG_REL_PATH


def default_config() -> Config:
    return Config(uuid=str(_uuid.uuid4()))


def write_config(root: Path, cfg: Config) -> None:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    include = ", ".join(f'"{x}"' for x in cfg.unit_include)
    exclude = ", ".join(f'"{x}"' for x in cfg.unit_exclude)

    content = "\n".join(
        [
            "[global]",
            f'uuid = "{cfg.uuid}"',
            f"compression_level = {cfg.compression_level}",
            f"max_workers = {cfg.max_workers}",
            f"default_encrypt = {str(cfg.default_encrypt).lower()}",
            "",
            "[protocol.github]",
            f"include_forks = {str(cfg.github_include_forks).lower()}",
            f"include_private = {str(cfg.github_include_private).lower()}",
            f"default_private_encrypt = {str(cfg.github_default_private_encrypt).lower()}",
            "",
            "[units]",
            f"include = [{include}]",
            f"exclude = [{exclude}]",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")


def _ensure_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("units.include/exclude must be list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("units.include/exclude entries must be string")
        out.append(item)
    return out


def load_config(root: Path) -> Config:
    path = config_path(root)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")

    data = tomllib.loads(path.read_text(encoding="utf-8"))

    global_cfg = data.get("global", {})
    protocol_cfg = data.get("protocol", {}).get("github", {})
    units_cfg = data.get("units", {})

    config_uuid = global_cfg.get("uuid", "")
    if not config_uuid:
        config_uuid = str(_uuid.uuid4())
        cfg = Config(
            uuid=config_uuid,
            compression_level=int(global_cfg.get("compression_level", 10)),
            max_workers=int(global_cfg.get("max_workers", 1)),
            default_encrypt=bool(global_cfg.get("default_encrypt", False)),
            github_include_forks=bool(protocol_cfg.get("include_forks", False)),
            github_include_private=bool(protocol_cfg.get("include_private", True)),
            github_default_private_encrypt=bool(
                protocol_cfg.get("default_private_encrypt", True)
            ),
            unit_include=_ensure_str_list(units_cfg.get("include")),
            unit_exclude=_ensure_str_list(units_cfg.get("exclude")),
        )
        write_config(root, cfg)
        return cfg

    return Config(
        uuid=config_uuid,
        compression_level=int(global_cfg.get("compression_level", 10)),
        max_workers=int(global_cfg.get("max_workers", 1)),
        default_encrypt=bool(global_cfg.get("default_encrypt", False)),
        github_include_forks=bool(protocol_cfg.get("include_forks", False)),
        github_include_private=bool(protocol_cfg.get("include_private", True)),
        github_default_private_encrypt=bool(
            protocol_cfg.get("default_private_encrypt", True)
        ),
        unit_include=_ensure_str_list(units_cfg.get("include")),
        unit_exclude=_ensure_str_list(units_cfg.get("exclude")),
    )
