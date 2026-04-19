from __future__ import annotations

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
