from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import backup_utilities.passphrase as passphrase

TEST_UUID = "123e4567-e89b-12d3-a456-426614174000"


def _reset_passphrase_state() -> None:
    passphrase.set_prompt_func(None)
    passphrase.configure_keyring_uuid(None)
    passphrase.clear_cached_passphrase()


def test_prompt_confirmed_passphrase_stores_in_configured_keyring(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_store(uuid: str, value: str) -> None:
        calls.append((uuid, value))

    monkeypatch.setattr(passphrase, "store_passphrase_in_keyring", fake_store)
    _reset_passphrase_state()
    passphrase.configure_keyring_uuid(TEST_UUID)
    answers = iter(["secret", "secret"])
    passphrase.set_prompt_func(lambda _prompt: next(answers))

    try:
        result = passphrase.prompt_new_passphrase(confirm=True)
        assert result == "secret"
        assert calls == [(TEST_UUID, "secret")]
        assert passphrase.get_passphrase(allow_prompt=False) == "secret"
    finally:
        _reset_passphrase_state()


def test_get_passphrase_uses_configured_keyring_when_cache_empty(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(uuid: str) -> str | None:
        calls.append(uuid)
        return "from-keyring"

    monkeypatch.setattr(passphrase, "get_passphrase_from_keyring", fake_get)
    _reset_passphrase_state()
    passphrase.configure_keyring_uuid(TEST_UUID)

    try:
        result = passphrase.get_passphrase(allow_prompt=False)
        assert result == "from-keyring"
        assert calls == [TEST_UUID]
        assert passphrase.get_passphrase(allow_prompt=False) == "from-keyring"
    finally:
        _reset_passphrase_state()


def test_configure_keyring_uuid_rejects_invalid_uuid() -> None:
    _reset_passphrase_state()
    try:
        try:
            passphrase.configure_keyring_uuid("test-uuid")
            raise AssertionError("expected invalid uuid")
        except ValueError as exc:
            assert str(exc) == "invalid keyring uuid"
    finally:
        _reset_passphrase_state()


def test_store_passphrase_creates_private_key_file(monkeypatch, tmp_path: Path) -> None:
    key_dir = tmp_path / "keyring-keys"
    monkeypatch.setattr(passphrase, "_KEY_DIR", key_dir)

    store_calls: list[tuple[str, str, str]] = []
    fake_keyring = SimpleNamespace(
        set_password=lambda service, username, password: store_calls.append(
            (service, username, password)
        ),
        get_password=lambda _service, _username: None,
    )
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)

    passphrase.store_passphrase_in_keyring(TEST_UUID, "secret")

    key_path = key_dir / f"{TEST_UUID}.key"
    assert key_path.exists()
    assert store_calls and store_calls[0][0] == "backup-utilities"
    assert store_calls[0][1] == TEST_UUID
    if os.name == "posix":
        mode = stat.S_IMODE(key_path.stat().st_mode)
        assert mode == 0o600


def test_get_passphrase_from_keyring_does_not_create_missing_key(
    monkeypatch, tmp_path: Path
) -> None:
    key_dir = tmp_path / "keyring-keys"
    key_path = key_dir / f"{TEST_UUID}.key"
    monkeypatch.setattr(passphrase, "_KEY_DIR", key_dir)

    fake_keyring = SimpleNamespace(
        set_password=lambda _service, _username, _password: None,
        get_password=lambda _service, _username: "encrypted-value",
    )
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)

    result = passphrase.get_passphrase_from_keyring(TEST_UUID)
    assert result is None
    assert not key_path.exists()


def test_get_passphrase_falls_back_to_prompt_when_keyring_read_fails(
    monkeypatch,
) -> None:
    def fail_read(_uuid: str) -> str | None:
        raise ValueError("decrypt failed")

    _reset_passphrase_state()
    passphrase.configure_keyring_uuid(TEST_UUID)
    passphrase.set_prompt_func(lambda _prompt: "typed-secret")
    monkeypatch.setattr(passphrase, "get_passphrase_from_keyring", fail_read)

    try:
        result = passphrase.get_passphrase(allow_prompt=True)
        assert result == "typed-secret"
    finally:
        _reset_passphrase_state()
