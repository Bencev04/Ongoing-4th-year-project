"""Fernet encryption helpers for API tokens stored in platform settings.

The encryption key is loaded from the ``NOTIFICATION_ENCRYPTION_KEY``
environment variable.  Generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("NOTIFICATION_ENCRYPTION_KEY", "")
        if not key:
            raise RuntimeError(
                "NOTIFICATION_ENCRYPTION_KEY is not set. "
                "Generate one with: python -c "
                '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return a URL-safe base64 token."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet token back to plaintext.

    Raises ``InvalidToken`` if the key is wrong or data is corrupted.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — wrong encryption key or corrupted data")
        raise
