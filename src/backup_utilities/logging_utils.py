from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
import threading

_lock = threading.Lock()


def daily_log_path(root: Path, day: date | None = None) -> Path:
    target_day = day or date.today()
    return root / "logs" / f"{target_day.isoformat()}.log"


def append_log(root: Path, source: str, message: str) -> Path:
    path = daily_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat()} [{source}] {message}\n"
    with _lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return path
