from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


@dataclass(slots=True)
class DialogResult:
    code: int
    value: str


class Whiptail:
    def __init__(self) -> None:
        if shutil.which("whiptail") is None:
            raise RuntimeError("whiptail is not installed")
        if not (sys.stdin.isatty() and sys.stderr.isatty()):
            raise RuntimeError("tui requires an interactive tty terminal")

    def _run(self, args: list[str]) -> DialogResult:
        read_fd, write_fd = os.pipe()
        try:
            cmd = ["whiptail", "--output-fd", str(write_fd), *args]
            res = subprocess.run(
                cmd,
                check=False,
                pass_fds=(write_fd,),
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            os.close(write_fd)
            value = self._read_capture_fd(read_fd)
            return DialogResult(code=res.returncode, value=value.strip())
        finally:
            for fd in (read_fd, write_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass

    @staticmethod
    def _read_capture_fd(fd: int) -> str:
        chunks: list[bytes] = []
        while True:
            data = os.read(fd, 4096)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks).decode("utf-8", errors="replace")

    def menu(self, title: str, text: str, options: list[tuple[str, str]]) -> str | None:
        args = [
            "--title",
            title,
            "--cancel-button",
            "Back",
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

    def checklist(
        self,
        title: str,
        text: str,
        options: list[tuple[str, str, bool]],
    ) -> list[str] | None:
        args = [
            "--title",
            title,
            "--cancel-button",
            "Back",
            "--checklist",
            text,
            "24",
            "120",
            "14",
        ]
        for tag, desc, enabled in options:
            args.extend([tag, desc, "ON" if enabled else "OFF"])

        out = self._run(args)
        if out.code != 0:
            return None

        value = out.value.strip()
        if not value:
            return []
        return shlex.split(value)

    def inputbox(self, title: str, text: str, default: str = "") -> str | None:
        args = [
            "--title",
            title,
            "--cancel-button",
            "Back",
            "--inputbox",
            text,
            "12",
            "90",
            default,
        ]
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
