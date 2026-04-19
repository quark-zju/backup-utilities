from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from .config import load_config
from .discovery import discover_units, format_discovered
from .layout import load_index
from .protocols import default_registry
from .recovery import decrypt_unit_payload
from .runner import run_backup, verify_units
from .selectors import select_add, select_decrypt, select_encrypt, select_remove


@dataclass(slots=True)
class DialogResult:
    code: int
    value: str


class Whiptail:
    def __init__(self) -> None:
        if shutil.which("whiptail") is None:
            raise RuntimeError("whiptail is not installed")

    def _run(self, args: list[str]) -> DialogResult:
        cmd = " ".join(shlex.quote(x) for x in ["whiptail", *args])
        cmd = f"{cmd} 3>&1 1>&2 2>&3"
        res = subprocess.run(
            cmd, shell=True, check=False, capture_output=True, text=True
        )
        return DialogResult(code=res.returncode, value=res.stdout.strip())

    def menu(self, title: str, text: str, options: list[tuple[str, str]]) -> str | None:
        args = [
            "--title",
            title,
            "--menu",
            text,
            "22",
            "90",
            "12",
        ]
        for tag, desc in options:
            args.extend([tag, desc])
        out = self._run(args)
        return out.value if out.code == 0 else None

    def inputbox(self, title: str, text: str, default: str = "") -> str | None:
        args = ["--title", title, "--inputbox", text, "12", "90", default]
        out = self._run(args)
        return out.value if out.code == 0 else None

    def yesno(self, title: str, text: str) -> bool:
        args = ["--title", title, "--yesno", text, "12", "90"]
        out = self._run(args)
        return out.code == 0

    def msgbox(self, title: str, text: str) -> None:
        self._run(["--title", title, "--msgbox", text, "18", "100"])

    def textbox(self, title: str, file_path: Path) -> None:
        self._run(["--title", title, "--textbox", str(file_path), "25", "110"])


def _status_text(root: Path) -> str:
    cfg = load_config(root)
    index = load_index(root)
    lines = [
        f"root: {root}",
        f"selected units: {len(cfg.unit_include)}",
        f"excluded units: {len(cfg.unit_exclude)}",
        f"forced encrypt units: {len(cfg.unit_encrypt)}",
        f"forced decrypt units: {len(cfg.unit_decrypt)}",
        f"indexed snapshots: {len(index)}",
    ]
    return "\n".join(lines)


def _discover_units(w: Whiptail) -> None:
    registry = default_registry()
    protocol = w.menu(
        "Discover",
        "Choose protocol",
        [(name, f"Discover {name} units") for name in registry.protocol_names()],
    )
    if not protocol:
        return

    user: str | None = None
    if protocol == "github":
        user_raw = w.inputbox(
            "Discover GitHub",
            "GitHub user/org (empty = infer from gh auth):",
            "",
        )
        user = user_raw if user_raw else None

    limit_raw = w.inputbox("Discover", "Max units:", "50")
    if not limit_raw:
        return

    limit = int(limit_raw)
    units = discover_units(registry, protocol, user=user, limit=limit)

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as tmp:
        tmp.write(f"protocol: {protocol}\n")
        tmp.write(f"found units: {len(units)}\n\n")
        for line in format_discovered(units):
            tmp.write(line)
            tmp.write("\n")
        tmp_path = Path(tmp.name)
    try:
        w.textbox("Discover Result", tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _input_unit_id(w: Whiptail, title: str) -> str | None:
    return w.inputbox(title, "Unit id (e.g. github/owner/repo):")


def run_tui(root: Path) -> int:
    w = Whiptail()

    while True:
        choice = w.menu(
            "Backup TUI",
            "Select action",
            [
                ("status", "Show status"),
                ("discover", "Discover units"),
                ("add", "Select unit"),
                ("remove", "Exclude unit"),
                ("encrypt", "Force unit encryption"),
                ("decrypt", "Force unit unencrypted"),
                ("run", "Run backup"),
                ("verify", "Verify payload checksums"),
                ("decrypt_unit", "Decrypt one unit payload"),
                ("exit", "Exit TUI"),
            ],
        )

        if choice is None or choice == "exit":
            return 0

        try:
            if choice == "status":
                w.msgbox("Status", _status_text(root))
            elif choice == "discover":
                _discover_units(w)
            elif choice == "add":
                unit_id = _input_unit_id(w, "Select Unit")
                if unit_id:
                    select_add(root, unit_id)
                    w.msgbox("Done", f"selected: {unit_id}")
            elif choice == "remove":
                unit_id = _input_unit_id(w, "Exclude Unit")
                if unit_id:
                    select_remove(root, unit_id)
                    w.msgbox("Done", f"excluded: {unit_id}")
            elif choice == "encrypt":
                unit_id = _input_unit_id(w, "Force Encrypt")
                if unit_id:
                    select_encrypt(root, unit_id)
                    w.msgbox("Done", f"force encrypt: {unit_id}")
            elif choice == "decrypt":
                unit_id = _input_unit_id(w, "Force Decrypt")
                if unit_id:
                    select_decrypt(root, unit_id)
                    w.msgbox("Done", f"force decrypt: {unit_id}")
            elif choice == "run":
                dry_run = w.yesno("Run Backup", "Run in dry-run mode?")
                code = run_backup(root, default_registry(), unit=None, dry_run=dry_run)
                w.msgbox("Run Result", f"run finished with code: {code}")
            elif choice == "verify":
                code = verify_units(root, unit=None)
                w.msgbox("Verify Result", f"verify finished with code: {code}")
            elif choice == "decrypt_unit":
                unit_id = _input_unit_id(w, "Decrypt Unit")
                if not unit_id:
                    continue
                out = w.inputbox(
                    "Decrypt Unit",
                    "Output path for decrypted tar.zst:",
                    str((root / "out" / "decrypted.tar.zst").resolve()),
                )
                if not out:
                    continue
                decrypt_unit_payload(root, unit_id, Path(out))
                w.msgbox("Done", f"decrypted to: {Path(out).resolve()}")
        except Exception as exc:
            w.msgbox("Error", str(exc))
