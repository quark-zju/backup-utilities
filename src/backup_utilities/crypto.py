from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
from getpass import getpass

KDF_N = 2**15
KDF_R = 8
KDF_P = 1
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12
CHUNK_SIZE = 1024 * 1024
MAGIC = b"BUENC1\n"


@dataclass(slots=True)
class EncryptResult:
    output_path: Path
    sha256_hex: str
    size_bytes: int
    encryption_metadata: dict[str, object]


def resolve_passphrase() -> str:
    env_value = os.environ.get("BACKUP_PASSPHRASE")
    if env_value:
        return env_value

    # Fallback for interactive runs without env var.
    value = getpass("Backup passphrase: ")
    if not value:
        raise ValueError("empty passphrase")
    return value


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except Exception as exc:
        raise RuntimeError(
            "cryptography is required for encryption; add dependency and install it"
        ) from exc

    kdf = Scrypt(salt=salt, length=KEY_LEN, n=KDF_N, r=KDF_R, p=KDF_P)
    return kdf.derive(passphrase.encode("utf-8"))


def _build_header(
    *,
    salt: bytes,
    nonce: bytes,
    aad: bytes,
) -> bytes:
    header = {
        "version": 1,
        "cipher": "aes-256-gcm",
        "kdf": {
            "name": "scrypt",
            "n": KDF_N,
            "r": KDF_R,
            "p": KDF_P,
            "salt_b64": b64encode(salt).decode("ascii"),
        },
        "nonce_b64": b64encode(nonce).decode("ascii"),
        "aad_sha256": sha256(aad).hexdigest(),
    }
    header_bytes = json.dumps(header, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return MAGIC + struct.pack("!I", len(header_bytes)) + header_bytes


def encrypt_file(
    *,
    input_path: Path,
    output_path: Path,
    passphrase: str,
    aad_context: dict[str, str],
) -> EncryptResult:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception as exc:
        raise RuntimeError(
            "cryptography is required for encryption; add dependency and install it"
        ) from exc

    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(passphrase, salt)

    aad = json.dumps(aad_context, sort_keys=True, separators=(",", ":")).encode("utf-8")
    header_prefix = _build_header(salt=salt, nonce=nonce, aad=aad)

    digest = sha256()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(aad)

    with input_path.open("rb") as src, output_path.open("wb") as dst:
        dst.write(header_prefix)
        digest.update(header_prefix)

        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            encrypted = encryptor.update(chunk)
            dst.write(encrypted)
            digest.update(encrypted)

        encryptor.finalize()
        tag = encryptor.tag
        dst.write(tag)
        digest.update(tag)

    size_bytes = output_path.stat().st_size
    metadata = {
        "format": "buenc-v1",
        "cipher": "aes-256-gcm",
        "kdf": {"name": "scrypt", "n": KDF_N, "r": KDF_R, "p": KDF_P},
    }
    return EncryptResult(
        output_path=output_path,
        sha256_hex=digest.hexdigest(),
        size_bytes=size_bytes,
        encryption_metadata=metadata,
    )
