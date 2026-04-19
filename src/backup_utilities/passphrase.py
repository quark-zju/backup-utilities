from __future__ import annotations

from base64 import b64decode, b64encode, urlsafe_b64encode
from getpass import getpass
import logging
import os
from pathlib import Path
import sys
import threading
import uuid as _uuid
from typing import Callable, Literal

PromptFunc = Callable[[str], str | None]
StoreStatus = Literal["stored", "failed", "skipped"]

_KEY_DIR = Path.home() / ".config" / "backup-utilities" / "keyring-keys"
_KEYRING_SERVICE = "backup-utilities"
_logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cached_passphrase: str | None = None
_prompt_func: PromptFunc | None = None
_env_passphrase: str | None = None
_env_initialized = False
_keyring_uuid: str | None = None


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


def _get_key_path(uuid: str) -> Path:
    return _KEY_DIR / f"{uuid}.key"


def _normalize_uuid(value: str) -> str:
    try:
        return str(_uuid.UUID(value))
    except ValueError as exc:
        raise ValueError("invalid keyring uuid") from exc


def _get_or_create_key(uuid: str) -> bytes:
    key_path = _get_key_path(uuid)
    if key_path.exists():
        _logger.debug("keyring key exists for uuid=%s path=%s", uuid, key_path)
        return key_path.read_bytes()
    key = os.urandom(32)
    _KEY_DIR.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    _logger.info("created keyring key for uuid=%s path=%s", uuid, key_path)
    return key


def _fernet_from_key(key: bytes):
    from cryptography.fernet import Fernet

    fernet_key = urlsafe_b64encode(key).decode("ascii")
    return Fernet(fernet_key.encode())


def _encrypt_passphrase(passphrase: str, key: bytes) -> str:
    f = _fernet_from_key(key)
    return b64encode(f.encrypt(passphrase.encode())).decode()


def _decrypt_passphrase(encrypted: str, key: bytes) -> str:
    f = _fernet_from_key(key)
    return f.decrypt(b64decode(encrypted)).decode()


def store_passphrase_in_keyring(uuid: str, passphrase: str) -> None:
    uuid = _normalize_uuid(uuid)
    _logger.info("attempt keyring write for uuid=%s", uuid)
    key = _get_or_create_key(uuid)
    encrypted = _encrypt_passphrase(passphrase, key)
    import keyring

    keyring.set_password(_KEYRING_SERVICE, uuid, encrypted)
    _logger.info("keyring write success for uuid=%s", uuid)


def get_passphrase_from_keyring(uuid: str) -> str | None:
    uuid = _normalize_uuid(uuid)
    _logger.debug("attempt keyring read for uuid=%s", uuid)
    import keyring

    encrypted = keyring.get_password(_KEYRING_SERVICE, uuid)
    if encrypted is None:
        _logger.debug("keyring read miss for uuid=%s", uuid)
        return None
    key = _get_or_create_key(uuid)
    plain = _decrypt_passphrase(encrypted, key)
    _logger.info("keyring read success for uuid=%s", uuid)
    return plain


def configure_keyring_uuid(uuid: str | None) -> None:
    global _keyring_uuid
    raw = uuid.strip() if uuid else ""
    normalized = _normalize_uuid(raw) if raw else ""
    with _lock:
        _keyring_uuid = normalized or None
    if normalized:
        _logger.info("configured keyring uuid=%s", normalized)
    else:
        _logger.info("cleared keyring uuid configuration")


def _configured_keyring_uuid() -> str | None:
    with _lock:
        return _keyring_uuid


def store_passphrase_for_configured_uuid(passphrase: str) -> StoreStatus:
    uuid = _configured_keyring_uuid()
    if not uuid:
        _logger.debug("skip keyring write: keyring uuid is not configured")
        return "skipped"

    try:
        store_passphrase_in_keyring(uuid, passphrase)
    except Exception:
        _logger.exception("keyring write failed for uuid=%s", uuid)
        return "failed"
    return "stored"


def cache_confirmed_passphrase(passphrase: str) -> StoreStatus:
    set_cached_passphrase(passphrase)
    return store_passphrase_for_configured_uuid(passphrase)


def get_passphrase_from_configured_keyring() -> str | None:
    uuid = _configured_keyring_uuid()
    if not uuid:
        _logger.debug("skip keyring read: keyring uuid is not configured")
        return None

    try:
        value = get_passphrase_from_keyring(uuid)
    except Exception:
        _logger.exception("keyring read failed for uuid=%s", uuid)
        return None
    if value:
        set_cached_passphrase(value)
    return value


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


def validate_new_passphrase(
    value: str,
    confirmation: str | None = None,
    *,
    require_confirmation: bool = False,
) -> str:
    if not value:
        raise ValueError("empty passphrase")
    if require_confirmation:
        if confirmation is None:
            raise ValueError("passphrase confirmation is required")
        if value != confirmation:
            raise ValueError("passphrase confirmation mismatch")
    return value


def _prompt_once(prompt: str) -> str:
    with _lock:
        func = _prompt_func

    if func is not None:
        value = func(prompt)
        if value is None:
            raise ValueError("passphrase input cancelled")
        return value

    return _prompt_in_cli(prompt)


def prompt_new_passphrase(
    prompt: str = "Backup passphrase: ",
    *,
    confirm: bool = False,
    confirm_prompt: str = "Confirm passphrase: ",
) -> str:
    value = _prompt_once(prompt)
    confirmation = _prompt_once(confirm_prompt) if confirm else None
    out = validate_new_passphrase(
        value,
        confirmation,
        require_confirmation=confirm,
    )
    if confirm:
        cache_confirmed_passphrase(out)
    else:
        set_cached_passphrase(out)
    return out


def get_passphrase(
    *,
    allow_prompt: bool = True,
    prompt: str = "Backup passphrase: ",
    confirm_new: bool = False,
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

    keyring_value = get_passphrase_from_configured_keyring()
    if keyring_value:
        return keyring_value

    if not allow_prompt:
        raise ValueError("passphrase unavailable")

    return prompt_new_passphrase(prompt, confirm=confirm_new)
