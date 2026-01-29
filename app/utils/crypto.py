"""
Encryption utilities for tenant credentials.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC).
Encryption key must be set via TENANT_ENCRYPTION_KEY env var.
"""
from __future__ import annotations

import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    """Get Fernet instance from environment key."""
    key = os.getenv("TENANT_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("TENANT_ENCRYPTION_KEY not set in environment")
    return Fernet(key.encode())


def encrypt_credentials(data: dict[str, Any]) -> bytes:
    """
    Encrypt a credentials dict to bytes.

    Args:
        data: Dict of credentials (e.g., {"access_token": "...", "location_id": "..."})

    Returns:
        Encrypted bytes suitable for storing in BYTEA column.
    """
    f = _get_fernet()
    json_bytes = json.dumps(data).encode("utf-8")
    return f.encrypt(json_bytes)


def decrypt_credentials(encrypted: bytes) -> dict[str, Any]:
    """
    Decrypt bytes back to credentials dict.

    Args:
        encrypted: Encrypted bytes from DB.

    Returns:
        Original credentials dict.

    Raises:
        InvalidToken: If decryption fails (wrong key or corrupted data).
    """
    f = _get_fernet()
    decrypted = f.decrypt(encrypted)
    return json.loads(decrypted.decode("utf-8"))


def generate_key() -> str:
    """
    Generate a new Fernet key.

    Run this once to create TENANT_ENCRYPTION_KEY:
        python -c "from app.utils.crypto import generate_key; print(generate_key())"
    """
    return Fernet.generate_key().decode()