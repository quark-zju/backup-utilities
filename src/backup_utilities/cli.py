from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .layout import init_root, load_index
from .protocols import default_registry
from .recovery import decrypt_unit_payload
from .runner import run_backup, verify_units
from .selectors import select_add, select_decrypt, select_encrypt, select_remove
from .tui import run_tui


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    init_root(root)
    print(f"initialized backup root: {root}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    index = load_index(root)

    print(f"root: {root}")
    print(f"selected units: {len(cfg.unit_include)}")
    print(f"excluded units: {len(cfg.unit_exclude)}")
    print(f"forced encrypt units: {len(cfg.unit_encrypt)}")
    print(f"forced decrypt units: {len(cfg.unit_decrypt)}")
    print(f"indexed snapshots: {len(index)}")
    return 0


def _cmd_discover_github(args: argparse.Namespace) -> int:
    protocol = default_registry().protocol_by_name("github")
    discovered = protocol.discover(user=args.user, limit=args.limit)
    print(f"found repos: {len(discovered)}")
    for item in discovered:
        print(
            "\t".join(
                [
                    item.unit_id,
                    f"fork={item.details.get('fork')}",
                    f"visibility={item.details.get('visibility')}",
                    f"default_selected={item.default_selected}",
                    f"default_encrypt={item.default_encrypt}",
                ]
            )
        )
    return 0


def _cmd_select_add(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    select_add(root, args.unit_id)
    print(f"selected: {args.unit_id}")
    return 0


def _cmd_select_remove(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    select_remove(root, args.unit_id)
    print(f"excluded: {args.unit_id}")
    return 0


def _cmd_select_encrypt(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    select_encrypt(root, args.unit_id)
    print(f"force encrypt: {args.unit_id}")
    return 0


def _cmd_select_decrypt(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    select_decrypt(root, args.unit_id)
    print(f"force decrypt: {args.unit_id}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    return run_backup(root, default_registry(), unit=args.unit, dry_run=args.dry_run)


def _cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    return verify_units(root, unit=args.unit)


def _cmd_decrypt_unit(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    out = Path(args.out).resolve()
    return decrypt_unit_payload(root=root, unit_id=args.unit, out=out)


def _cmd_tui(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    return run_tui(root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup", description="Unit-based incremental backup"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Initialize backup root")
    p_init.add_argument("--root", required=True, help="Backup root path")
    p_init.set_defaults(func=_cmd_init)

    p_status = subparsers.add_parser("status", help="Show backup status")
    p_status.add_argument("--root", required=True, help="Backup root path")
    p_status.set_defaults(func=_cmd_status)

    p_discover = subparsers.add_parser("discover", help="Discover backup units")
    discover_subparsers = p_discover.add_subparsers(
        dest="discover_command", required=True
    )

    p_discover_github = discover_subparsers.add_parser(
        "github", help="Discover GitHub repos"
    )
    p_discover_github.add_argument("--user", required=True, help="GitHub user or org")
    p_discover_github.add_argument("--limit", type=int, default=1000, help="Max repos")
    p_discover_github.set_defaults(func=_cmd_discover_github)

    p_select = subparsers.add_parser("select", help="Select or exclude backup units")
    select_subparsers = p_select.add_subparsers(dest="select_command", required=True)

    p_select_add = select_subparsers.add_parser("add", help="Add unit to include list")
    p_select_add.add_argument("--root", required=True, help="Backup root path")
    p_select_add.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_add.set_defaults(func=_cmd_select_add)

    p_select_remove = select_subparsers.add_parser(
        "remove", help="Move unit to exclude list"
    )
    p_select_remove.add_argument("--root", required=True, help="Backup root path")
    p_select_remove.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_remove.set_defaults(func=_cmd_select_remove)

    p_select_encrypt = select_subparsers.add_parser(
        "encrypt", help="Force unit encryption"
    )
    p_select_encrypt.add_argument("--root", required=True, help="Backup root path")
    p_select_encrypt.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_encrypt.set_defaults(func=_cmd_select_encrypt)

    p_select_decrypt = select_subparsers.add_parser(
        "decrypt", help="Force unit unencrypted payload"
    )
    p_select_decrypt.add_argument("--root", required=True, help="Backup root path")
    p_select_decrypt.add_argument("unit_id", help="Unit id like github/owner/repo")
    p_select_decrypt.set_defaults(func=_cmd_select_decrypt)

    p_run = subparsers.add_parser("run", help="Run backup")
    p_run.add_argument("--root", required=True, help="Backup root path")
    p_run.add_argument("--unit", help="Single selected unit to run")
    p_run.add_argument("--dry-run", action="store_true", help="Only check changes")
    p_run.set_defaults(func=_cmd_run)

    p_verify = subparsers.add_parser("verify", help="Verify payload sha256 by metadata")
    p_verify.add_argument("--root", required=True, help="Backup root path")
    p_verify.add_argument("--unit", help="Single selected unit to verify")
    p_verify.set_defaults(func=_cmd_verify)

    p_decrypt_unit = subparsers.add_parser(
        "decrypt-unit", help="Decrypt encrypted payload for one unit"
    )
    p_decrypt_unit.add_argument("--root", required=True, help="Backup root path")
    p_decrypt_unit.add_argument("--unit", required=True, help="Unit id to decrypt")
    p_decrypt_unit.add_argument(
        "--out", required=True, help="Output tar.zst path for decrypted payload"
    )
    p_decrypt_unit.set_defaults(func=_cmd_decrypt_unit)

    p_tui = subparsers.add_parser("tui", help="Start whiptail TUI")
    p_tui.add_argument("--root", required=True, help="Backup root path")
    p_tui.set_defaults(func=_cmd_tui)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
