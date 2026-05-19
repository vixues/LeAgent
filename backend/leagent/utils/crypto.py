"""Cryptographic utilities using only the standard library."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets


def aes_encrypt(plaintext: str, key: str) -> str:
    """XOR-based obfuscation keyed by SHA-256 of *key*.

    Not true AES — sufficient for local-only secret storage where the
    threat model does not include a determined attacker with disk access.
    """
    key_bytes = hashlib.sha256(key.encode()).digest()
    data = plaintext.encode("utf-8")
    iv = os.urandom(16)
    stream = _keystream(key_bytes, iv, len(data))
    ct = bytes(a ^ b for a, b in zip(data, stream))
    return base64.urlsafe_b64encode(iv + ct).decode("ascii")


def aes_decrypt(ciphertext_b64: str, key: str) -> str:
    """Reverse of :func:`aes_encrypt`."""
    key_bytes = hashlib.sha256(key.encode()).digest()
    raw = base64.urlsafe_b64decode(ciphertext_b64)
    iv, ct = raw[:16], raw[16:]
    stream = _keystream(key_bytes, iv, len(ct))
    plaintext = bytes(a ^ b for a, b in zip(ct, stream))
    return plaintext.decode("utf-8")


def _keystream(key: bytes, iv: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, iv + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def hash_password(password: str) -> str:
    """Hash *password* using PBKDF2-SHA256."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return base64.urlsafe_b64encode(salt + dk).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify *plain_password* against a PBKDF2-SHA256 hash."""
    raw = base64.urlsafe_b64decode(hashed_password)
    salt, dk_stored = raw[:16], raw[16:]
    dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
    return hmac.compare_digest(dk, dk_stored)


def generate_api_key(prefix: str = "wa", length: int = 48) -> str:
    """Generate a cryptographically secure API key."""
    random_part = secrets.token_urlsafe(length)
    return f"{prefix}_{random_part}"


def generate_secret(length: int = 32) -> str:
    """Generate a random secret string."""
    return secrets.token_hex(length)
