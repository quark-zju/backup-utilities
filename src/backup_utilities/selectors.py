from __future__ import annotations

from pathlib import Path

from .config import load_config, write_config
from .recovery import set_unit_payload_encryption


def select_add(root: Path, unit_id: str) -> None:
    cfg = load_config(root)

    if unit_id not in cfg.unit_include:
        cfg.unit_include.append(unit_id)
    if unit_id in cfg.unit_exclude:
        cfg.unit_exclude.remove(unit_id)

    cfg.unit_include.sort()
    cfg.unit_exclude.sort()
    write_config(root, cfg)


def select_remove(root: Path, unit_id: str) -> None:
    cfg = load_config(root)

    if unit_id in cfg.unit_include:
        cfg.unit_include.remove(unit_id)
    if unit_id not in cfg.unit_exclude:
        cfg.unit_exclude.append(unit_id)

    cfg.unit_include.sort()
    cfg.unit_exclude.sort()
    write_config(root, cfg)


def select_exclude(root: Path, unit_id: str) -> None:
    cfg = load_config(root)

    if unit_id not in cfg.unit_exclude:
        cfg.unit_exclude.append(unit_id)

    cfg.unit_exclude.sort()
    write_config(root, cfg)


def select_unexclude(root: Path, unit_id: str) -> None:
    cfg = load_config(root)

    if unit_id in cfg.unit_exclude:
        cfg.unit_exclude.remove(unit_id)

    cfg.unit_exclude.sort()
    write_config(root, cfg)


def select_encrypt(root: Path, unit_id: str, *, passphrase: str | None = None) -> str:
    cfg = load_config(root)
    if unit_id in cfg.unit_decrypt:
        cfg.unit_decrypt.remove(unit_id)
        cfg.unit_decrypt.sort()
        write_config(root, cfg)
    return set_unit_payload_encryption(root, unit_id, True, passphrase=passphrase)


def select_decrypt(root: Path, unit_id: str, *, passphrase: str | None = None) -> str:
    cfg = load_config(root)
    if unit_id in cfg.unit_encrypt:
        cfg.unit_encrypt.remove(unit_id)
        cfg.unit_encrypt.sort()
        write_config(root, cfg)
    return set_unit_payload_encryption(root, unit_id, False, passphrase=passphrase)
