"""Fernet-based encryption for sensitive data at rest — moved from app/core/encryption.py."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from common.configuration import get_configuration


class EncryptionService:
    """Fernet-based symmetric encryption for sensitive data."""

    def __init__(self, master_key: str) -> None:
        if not master_key:
            raise ValueError("Encryption key cannot be empty")
        key_bytes = hashlib.sha256(master_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            raise ValueError("Cannot decrypt empty string")
        return self._fernet.decrypt(ciphertext.encode()).decode()


_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Return the singleton EncryptionService, initialised from ENCRYPTION_KEY env var."""
    global _encryption_service
    if _encryption_service is None:
        encryption_key = get_configuration().runtime_configuration.encryption_key
        if not encryption_key:
            raise ValueError("Runtime encryption_key must be configured")
        _encryption_service = EncryptionService(encryption_key)
    return _encryption_service


def mask_api_key(api_key: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """Return a display hint for an API key, e.g. 'AKIA...XYZ1'."""
    if len(api_key) <= prefix_len + suffix_len:
        return "*" * len(api_key)
    return f"{api_key[:prefix_len]}...{api_key[-suffix_len:]}"
