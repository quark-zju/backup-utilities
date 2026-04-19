from __future__ import annotations

from getpass import getpass
import os
import sys
import threading
from typing import Callable

PromptFunc = Callable[[str], str | None]

_lock = threading.Lock()
_cached_passphrase: str | None = None
_prompt_func: PromptFunc | None = None
_env_passphrase: str | None = None
_env_initialized = False


def initialize_from_env() -> None:
    """Capture BACKUP_PASSPHRASE into process memory and unset env var.

    This is intentionally idempotent so callers can invoke it early in process startup.
    """
    global _env_initialized, _env_passphrase
    with _lock:
        if _env_initialized:
            return
        _env_initialized = True
        value = os.environ.pop("BACKUP_PASSPHRASE", None)
        if value:
            _env_passphrase = value


def set_prompt_func(func: PromptFunc | None) -> None:
    global _prompt_func
    with _lock:
        _prompt_func = func


def set_cached_passphrase(value: str | None) -> None:
    global _cached_passphrase
    with _lock:
        _cached_passphrase = value


def clear_cached_passphrase() -> None:
    global _env_passphrase
    set_cached_passphrase(None)
    with _lock:
        _env_passphrase = None


def has_passphrase_cached() -> bool:
    initialize_from_env()
    with _lock:
        return bool(_env_passphrase or _cached_passphrase)


def _prompt_in_cli(prompt: str) -> str:
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        raise ValueError(
            "missing passphrase in non-interactive mode; set BACKUP_PASSPHRASE"
        )
    value = getpass(prompt)
    if not value:
        raise ValueError("empty passphrase")
    return value


def prompt_new_passphrase(prompt: str = "Backup passphrase: ") -> str:
    with _lock:
        func = _prompt_func

    if func is not None:
        value = func(prompt)
        if value is None:
            raise ValueError("passphrase input cancelled")
        if not value:
            raise ValueError("empty passphrase")
    else:
        value = _prompt_in_cli(prompt)

    set_cached_passphrase(value)
    return value


def get_passphrase(
    *, allow_prompt: bool = True, prompt: str = "Backup passphrase: "
) -> str:
    initialize_from_env()
    with _lock:
        env_value = _env_passphrase
    if env_value:
        return env_value

    with _lock:
        cached = _cached_passphrase
    if cached:
        return cached

    if not allow_prompt:
        raise ValueError("passphrase unavailable")

    return prompt_new_passphrase(prompt)
