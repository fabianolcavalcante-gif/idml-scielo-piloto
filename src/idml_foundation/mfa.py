from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from idml_foundation.settings import Settings


def _fernet(settings: Settings) -> Fernet:
    configured = settings.mfa_encryption_key.get_secret_value().encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(configured).digest())
    return Fernet(key)


def encrypt_secret(secret: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(ciphertext: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext.encode("ascii")).decode("ascii")
    except InvalidToken as exc:
        raise ValueError("MFA secret cannot be decrypted") from exc


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, email: str, issuer: str = "IDML SciELO") -> str:
    label = quote(f"{issuer}:{email}", safe="")
    encoded_issuer = quote(issuer, safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={encoded_issuer}&digits=6&period=30"


def _decode_base32(secret: str) -> bytes:
    padding = "=" * (-len(secret) % 8)
    return base64.b32decode(secret + padding, casefold=True)


def totp_at(secret: str, counter: int) -> str:
    digest = hmac.new(_decode_base32(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def verify_totp(
    secret: str,
    code: str,
    *,
    last_counter: int | None = None,
    timestamp: int | None = None,
) -> int | None:
    if not code.isdigit() or len(code) != 6:
        return None
    current = (timestamp if timestamp is not None else int(time.time())) // 30
    for counter in (current - 1, current, current + 1):
        if last_counter is not None and counter <= last_counter:
            continue
        if hmac.compare_digest(totp_at(secret, counter), code):
            return counter
    return None


def generate_recovery_codes(count: int = 10) -> tuple[str, ...]:
    return tuple(f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count))


def hash_recovery_code(code: str, settings: Settings) -> str:
    key = settings.mfa_encryption_key.get_secret_value().encode()
    normalized = code.strip().casefold().encode()
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()


def consume_recovery_code(
    code: str, stored_hashes: list[str], settings: Settings
) -> tuple[bool, list[str]]:
    candidate = hash_recovery_code(code, settings)
    matched = next(
        (value for value in stored_hashes if hmac.compare_digest(value, candidate)),
        None,
    )
    if matched is None:
        return False, stored_hashes
    return True, [value for value in stored_hashes if value != matched]
