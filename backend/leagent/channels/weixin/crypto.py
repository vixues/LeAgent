"""AES-128-ECB helpers for WeChat iLink CDN media."""

from __future__ import annotations

import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """Apply PKCS#7 padding."""
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def pkcs7_unpad(data: bytes) -> bytes:
    """Remove PKCS#7 padding if valid."""
    if not data:
        return data
    pad_len = data[-1]
    if 1 <= pad_len <= 16 and data.endswith(bytes([pad_len]) * pad_len):
        return data[:-pad_len]
    return data


def aes_padded_size(size: int) -> int:
    """Encrypted ciphertext size for *size* plaintext bytes."""
    return ((size + 1 + 15) // 16) * 16


def parse_aes_key(aes_key: str) -> bytes:
    """Decode an iLink AES key (raw base64, base64(hex), or bare hex)."""
    raw = (aes_key or "").strip()
    if not raw:
        raise ValueError("empty aes_key")

    if len(raw) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in raw):
        return bytes.fromhex(raw)

    decoded = base64.b64decode(raw)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        text = decoded.decode("ascii", errors="ignore")
        if text and all(ch in "0123456789abcdefABCDEF" for ch in text):
            return bytes.fromhex(text)
    raise ValueError(f"unexpected aes_key format ({len(decoded)} decoded bytes)")


def aes128_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt with AES-128-ECB + PKCS#7."""
    if len(key) != 16:
        raise ValueError(f"AES-128 key must be 16 bytes, got {len(key)}")
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(pkcs7_pad(plaintext)) + encryptor.finalize()


def aes128_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt AES-128-ECB + PKCS#7 ciphertext."""
    if len(key) != 16:
        raise ValueError(f"AES-128 key must be 16 bytes, got {len(key)}")
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    return pkcs7_unpad(padded)
