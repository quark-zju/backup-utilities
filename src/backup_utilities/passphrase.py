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


def set_prompt_func(func: PromptFunc | None) -> None:
    global _prompt_func
    with _lock:
        _prompt_func = func


def set_cached_passphrase(value: str | None) -> None:
    global _cached_passphrase
    with _lock:
        _cached_passphrase = value


def clear_cached_passphrase() -> None:
    set_cached_passphrase(None)


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
    env_value = os.environ.get("BACKUP_PASSPHRASE")
    if env_value:
        return env_value

    with _lock:
        cached = _cached_passphrase
    if cached:
        return cached

    if not allow_prompt:
        raise ValueError("passphrase unavailable")

    return prompt_new_passphrase(prompt)
