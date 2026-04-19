from __future__ import annotations

import argparse
import os
from pathlib import Path
import traceback

from .config import load_config
from .discovery import discover_units, format_discovered
from .layout import init_root, load_index
from .logging_utils import append_log
from .passphrase import initialize_from_env
from .protocols import default_registry
from .recovery import decrypt_unit_payload
from .runner import run_backup, verify_units
from .selectors import (
    select_add,
    select_decrypt,
    select_encrypt,
    select_exclude,
    select_remove,
    select_unexclude,
)


def _resolve_root(args: argparse.Namespace) -> Path:
    root_raw = args.root or os.environ.get("BACKUP_ROOT")
    if not root_raw:
        raise ValueError("backup root is required: pass --root or set BACKUP_ROOT")
    return Path(root_raw).resolve()


def _resolve_root_if_available(args: argparse.Namespace) -> Path | None:
    if hasattr(args, "root"):
        root_raw = args.root or os.environ.get("BACKUP_ROOT")
        if root_raw:
            return Path(root_raw).resolve()
    return None


def _command_label(args: argparse.Namespace) -> str:
    parts = [str(args.command)]
    if hasattr(args, "discover_command") and args.discover_command:
        parts.append(str(args.discover_command))
    if hasattr(args, "select_command") and args.select_command:
        parts.append(str(args.select_command))
    if hasattr(args, "protocol") and args.protocol:
        parts.append(str(args.protocol))
    return " ".join(parts)


def _cmd_init(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    init_root(root)
    print(f"initialized backup root: {root}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    cfg = load_config(root)
    index = load_index(root)

    print(f"root: {root}")
    print(f"selected units: {len(cfg.unit_include)}")
    print(f"excluded units: {len(cfg.unit_exclude)}")
    print(f"legacy force-encrypt entries: {len(cfg.unit_encrypt)}")
    print(f"legacy force-decrypt entries: {len(cfg.unit_decrypt)}")
    print(f"indexed snapshots: {len(index)}")
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    registry = default_registry()
    discovered = discover_units(
        registry,
        args.protocol,
        user=args.user,
        limit=args.limit,
    )
    print(f"found units: {len(discovered)}")
    for line in format_discovered(discovered):
        print(line)
    return 0


def _cmd_select_add(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    select_add(root, args.unit_id)
    print(f"selected: {args.unit_id}")
    return 0


def _cmd_select_remove(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    select_remove(root, args.unit_id)
    print(f"excluded: {args.unit_id}")
    return 0


def _cmd_select_exclude(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    select_exclude(root, args.unit_id)
    print(f"excluded (keep include): {args.unit_id}")
    return 0


def _cmd_select_unexclude(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    select_unexclude(root, args.unit_id)
    print(f"unexcluded: {args.unit_id}")
    return 0


def _cmd_select_encrypt(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    result = select_encrypt(root, args.unit_id)
    print(f"encrypt: {args.unit_id}: {result}")
    return 0


def _cmd_select_decrypt(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    result = select_decrypt(root, args.unit_id)
    print(f"decrypt: {args.unit_id}: {result}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    return run_backup(root, default_registry(), unit=args.unit, dry_run=args.dry_run)


def _cmd_verify(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    return verify_units(root, unit=args.unit)


def _cmd_decrypt_unit(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    out = Path(args.out).resolve()
    return decrypt_unit_payload(root=root, unit_id=args.unit, out=out)


def _cmd_tui(args: argparse.Namespace) -> int:
    root = _resolve_root(args)
    try:
        from .ui_textual import run_tui
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            raise RuntimeError(
                "textual is not installed; run dependency sync first (e.g. uv sync)"
            ) from exc
        raise

    return run_tui(root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup", description="Unit-based incremental backup"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Initialize backup root")
    p_init.add_argument("--root", help="Backup root path (fallback: BACKUP_ROOT)")
    p_init.set_defaults(func=_cmd_init)

    p_status = subparsers.add_parser("status", help="Show backup status")
    p_status.add_argument("--root", help="Backup root path (fallback: BACKUP_ROOT)")
    p_status.set_defaults(func=_cmd_status)

    registry = default_registry()

    p_discover = subparsers.add_parser("discover", help="Discover backup units")
    p_discover.add_argument(
        "protocol", choices=registry.protocol_names(), help="Protocol name"
    )
    p_discover.add_argument(
        "--user", help="GitHub user or org (default: infer from gh auth)"
    )
    p_discover.add_argument("--limit", type=int, default=1000, help="Max discover size")
    p_discover.set_defaults(func=_cmd_discover)

    p_select = subparsers.add_parser("select", help="Select or exclude backup units")
    select_subparsers = p_select.add_subparsers(dest="select_command", required=True)

    p_select_add = select_subparsers.add_parser("add", help="Add unit to include list")
    p_select_add.add_argument("--root", help="Backup root path (fallback: BACKUP_ROOT)")
    p_select_add.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_add.set_defaults(func=_cmd_select_add)

    p_select_remove = select_subparsers.add_parser(
        "remove", help="Move unit to exclude list"
    )
    p_select_remove.add_argument(
        "--root", help="Backup root path (fallback: BACKUP_ROOT)"
    )
    p_select_remove.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_remove.set_defaults(func=_cmd_select_remove)

    p_select_exclude = select_subparsers.add_parser(
        "exclude", help="Add unit to exclude list without changing include list"
    )
    p_select_exclude.add_argument(
        "--root", help="Backup root path (fallback: BACKUP_ROOT)"
    )
    p_select_exclude.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_exclude.set_defaults(func=_cmd_select_exclude)

    p_select_unexclude = select_subparsers.add_parser(
        "unexclude", help="Remove unit from exclude list"
    )
    p_select_unexclude.add_argument(
        "--root", help="Backup root path (fallback: BACKUP_ROOT)"
    )
    p_select_unexclude.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_unexclude.set_defaults(func=_cmd_select_unexclude)

    p_select_encrypt = select_subparsers.add_parser(
        "encrypt", help="Force unit encryption"
    )
    p_select_encrypt.add_argument(
        "--root", help="Backup root path (fallback: BACKUP_ROOT)"
    )
    p_select_encrypt.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_encrypt.set_defaults(func=_cmd_select_encrypt)

    p_select_decrypt = select_subparsers.add_parser(
        "decrypt", help="Force unit unencrypted payload"
    )
    p_select_decrypt.add_argument(
        "--root", help="Backup root path (fallback: BACKUP_ROOT)"
    )
    p_select_decrypt.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_decrypt.set_defaults(func=_cmd_select_decrypt)

    p_run = subparsers.add_parser("run", help="Run backup")
    p_run.add_argument("--root", help="Backup root path (fallback: BACKUP_ROOT)")
    p_run.add_argument("--unit", help="Single selected unit to run")
    p_run.add_argument("--dry-run", action="store_true", help="Only check changes")
    p_run.set_defaults(func=_cmd_run)

    p_verify = subparsers.add_parser("verify", help="Verify payload sha256 by metadata")
    p_verify.add_argument("--root", help="Backup root path (fallback: BACKUP_ROOT)")
    p_verify.add_argument("--unit", help="Single selected unit to verify")
    p_verify.set_defaults(func=_cmd_verify)

    p_decrypt_unit = subparsers.add_parser(
        "decrypt-unit", help="Decrypt encrypted payload for one unit"
    )
    p_decrypt_unit.add_argument(
        "--root", help="Backup root path (fallback: BACKUP_ROOT)"
    )
    p_decrypt_unit.add_argument("--unit", required=True, help="Unit id to decrypt")
    p_decrypt_unit.add_argument(
        "--out", required=True, help="Output tar.zst path for decrypted payload"
    )
    p_decrypt_unit.set_defaults(func=_cmd_decrypt_unit)

    p_tui = subparsers.add_parser("tui", help="Start Textual TUI")
    p_tui.add_argument("--root", help="Backup root path (fallback: BACKUP_ROOT)")
    p_tui.set_defaults(func=_cmd_tui)

    return parser


def main() -> int:
    initialize_from_env()
    parser = build_parser()
    args = parser.parse_args()
    root = _resolve_root_if_available(args)
    label = _command_label(args)
    if root is not None:
        append_log(root, "cli", f"START {label}")
    try:
        code = args.func(args)
    except Exception as exc:
        if root is not None:
            append_log(root, "cli", f"ERROR {label}: {exc}")
            append_log(root, "cli", traceback.format_exc().strip())
        raise

    if root is not None:
        append_log(root, "cli", f"END {label} exit={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
