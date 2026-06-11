"""
Transparent encryption for SQLAlchemy string columns using Fernet (symmetric).

Usage in models:
    from app.utils.crypto import EncryptedString

    api_key = db.Column(EncryptedString(512), nullable=True)

Read/write works transparently – values are encrypted on write and decrypted on read.
Existing plaintext data is handled gracefully (decryption failure falls back to raw value).
"""
import os
import hashlib
import base64
import threading
from sqlalchemy import TypeDecorator, Text
from cryptography.fernet import Fernet, InvalidToken


# ── Key management ───────────────────────────────────────────────────────

_fernet_instance = None
_fernet_lock = threading.Lock()


def _get_encryption_key() -> bytes:
    """Return a Fernet-compatible 32-byte key.

    Resolves in order:
      1. ENCRYPTION_KEY env var (explicit, recommended)
      2. SHA256(SECRET_KEY) as fallback
    """
    key = os.environ.get("ENCRYPTION_KEY")
    if key:
        return key.encode() if isinstance(key, str) else key
    # Fallback: derive deterministic key from SECRET_KEY
    secret = os.environ.get("SECRET_KEY", "dev-fallback-insecure-key")
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance (thread-safe)."""
    global _fernet_instance
    if _fernet_instance is None:
        with _fernet_lock:
            if _fernet_instance is None:
                _fernet_instance = Fernet(_get_encryption_key())
    return _fernet_instance


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns Fernet token as str."""
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token. Returns plaintext.

    If the value is not a valid Fernet token (e.g. legacy plaintext),
    returns it as-is.
    """
    if not ciphertext:
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ciphertext


# ── SQLAlchemy TypeDecorator ─────────────────────────────────────────────

class EncryptedString(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts/decrypts values.

    impl:  Text (no length limit, works across SQLite/MySQL/PostgreSQL)
    cache_ok = True (safe for SQLAlchemy 2.0 cached compilation)
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt on write."""
        if value is None:
            return None
        return encrypt(value)

    def process_result_value(self, value, dialect):
        """Decrypt on read – falls back to plaintext for legacy data."""
        if value is None:
            return None
        return decrypt(value)

    def copy(self, **kwargs):
        return EncryptedString()
