from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
from getpass import getpass
import sys

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


@dataclass(slots=True)
class DecryptResult:
    output_path: Path
    sha256_hex: str
    size_bytes: int


def resolve_passphrase() -> str:
    env_value = os.environ.get("BACKUP_PASSPHRASE")
    if env_value:
        return env_value

    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        raise ValueError(
            "missing passphrase in non-interactive mode; set BACKUP_PASSPHRASE"
        )

    # Fallback for interactive TTY runs without env var.
    value = getpass("Backup passphrase: ")
    if not value:
        raise ValueError("empty passphrase")
    return value


def _derive_key(passphrase: str, salt: bytes, *, n: int, r: int, p: int) -> bytes:
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except Exception as exc:
        raise RuntimeError(
            "cryptography is required for encryption; add dependency and install it"
        ) from exc

    kdf = Scrypt(salt=salt, length=KEY_LEN, n=n, r=r, p=p)
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
    key = _derive_key(passphrase, salt, n=KDF_N, r=KDF_R, p=KDF_P)

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


def _read_header(input_path: Path) -> tuple[dict[str, object], int]:
    with input_path.open("rb") as src:
        magic = src.read(len(MAGIC))
        if magic != MAGIC:
            raise ValueError("invalid encrypted payload magic")
        length_raw = src.read(4)
        if len(length_raw) != 4:
            raise ValueError("invalid encrypted payload header length")
        header_len = struct.unpack("!I", length_raw)[0]
        header_bytes = src.read(header_len)
        if len(header_bytes) != header_len:
            raise ValueError("truncated encrypted payload header")
    header = json.loads(header_bytes.decode("utf-8"))
    return header, len(MAGIC) + 4 + header_len


def decrypt_file(
    *,
    input_path: Path,
    output_path: Path,
    passphrase: str,
    aad_context: dict[str, str],
) -> DecryptResult:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception as exc:
        raise RuntimeError(
            "cryptography is required for encryption; add dependency and install it"
        ) from exc

    header, header_size = _read_header(input_path)
    total_size = input_path.stat().st_size
    if total_size < header_size + 16:
        raise ValueError("encrypted payload is too short")

    aad = json.dumps(aad_context, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected_aad_hash = str(header.get("aad_sha256", ""))
    if sha256(aad).hexdigest() != expected_aad_hash:
        raise ValueError("aad mismatch for encrypted payload")

    kdf = header.get("kdf", {})
    if not isinstance(kdf, dict):
        raise ValueError("invalid kdf header")
    salt = b64decode(str(kdf.get("salt_b64", "")).encode("ascii"))
    n = int(kdf.get("n", KDF_N))
    r = int(kdf.get("r", KDF_R))
    p = int(kdf.get("p", KDF_P))
    key = _derive_key(passphrase, salt, n=n, r=r, p=p)

    nonce = b64decode(str(header.get("nonce_b64", "")).encode("ascii"))
    if len(nonce) != NONCE_LEN:
        raise ValueError("invalid nonce length")

    tag_offset = total_size - 16
    with input_path.open("rb") as src:
        src.seek(tag_offset)
        tag = src.read(16)

    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    decryptor.authenticate_additional_data(aad)

    digest = sha256()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    remaining = tag_offset - header_size

    with input_path.open("rb") as src, output_path.open("wb") as dst:
        src.seek(header_size)
        while remaining > 0:
            take = min(CHUNK_SIZE, remaining)
            chunk = src.read(take)
            if not chunk:
                raise ValueError("unexpected EOF while reading ciphertext")
            remaining -= len(chunk)
            plain = decryptor.update(chunk)
            dst.write(plain)
            digest.update(plain)
        decryptor.finalize()

    size_bytes = output_path.stat().st_size
    return DecryptResult(
        output_path=output_path,
        sha256_hex=digest.hexdigest(),
        size_bytes=size_bytes,
    )
