from __future__ import annotations

from datetime import date, datetime
import logging
from pathlib import Path
import threading
from typing import TextIO

_lock = threading.Lock()
_logger_lock = threading.Lock()
_root_loggers: dict[Path, logging.Logger] = {}


def daily_log_path(root: Path, day: date | None = None) -> Path:
    target_day = day or date.today()
    return root / "logs" / f"{target_day.isoformat()}.log"


class _IsoFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return datetime.fromtimestamp(record.created).isoformat()


class _DailyFileHandler(logging.Handler):
    def __init__(self, root: Path) -> None:
        super().__init__(level=logging.INFO)
        self._root = root
        self._day: date | None = None
        self._path: Path | None = None
        self._stream: TextIO | None = None
        self._handler_lock = threading.Lock()

    def _ensure_stream(self) -> Path:
        today = date.today()
        if self._stream is not None and self._day == today and self._path is not None:
            return self._path

        if self._stream is not None:
            self._stream.close()
            self._stream = None

        path = daily_log_path(self._root, today)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = path.open("a", encoding="utf-8")
        self._day = today
        self._path = path
        return path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._handler_lock:
                self._ensure_stream()
                if self._stream is None:
                    return
                self._stream.write(msg + "\n")
                self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self._handler_lock:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        super().close()


def _root_logger(root: Path) -> logging.Logger:
    key = root.resolve()
    with _logger_lock:
        logger = _root_loggers.get(key)
        if logger is not None:
            return logger

        logger = logging.getLogger(f"backup_utilities.root.{key}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()

        handler = _DailyFileHandler(key)
        handler.setFormatter(_IsoFormatter("%(asctime)s [%(source)s] %(message)s"))
        logger.addHandler(handler)
        _root_loggers[key] = logger
        return logger


def get_source_logger(root: Path, source: str) -> logging.LoggerAdapter:
    base = _root_logger(root)
    return logging.LoggerAdapter(base, {"source": source})


def append_log(root: Path, source: str, message: str) -> Path:
    logger = get_source_logger(root, source)
    with _lock:
        logger.info(message)
    return daily_log_path(root)
