from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .layout import init_root, load_index


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
    print(f"indexed snapshots: {len(index)}")
    return 0


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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
