"""Tests for Fernet encryption / decryption helpers."""

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.encryption import decrypt_value, encrypt_value


class TestEncryption:
    """Round-trip and error-path tests for encrypt/decrypt."""

    @pytest.fixture(autouse=True)
    def _set_encryption_key(self, monkeypatch):
        """Generate a fresh Fernet key for each test."""
        self.key = Fernet.generate_key().decode()
        monkeypatch.setenv("NOTIFICATION_ENCRYPTION_KEY", self.key)
        # Reset module-level cached Fernet instance
        import app.encryption as enc_mod

        enc_mod._fernet = None

    def test_round_trip_ascii(self):
        plain = "my-secret-token"
        encrypted = encrypt_value(plain)
        assert encrypted != plain
        assert decrypt_value(encrypted) == plain

    def test_round_trip_unicode(self):
        plain = "Fáilte 🎉"
        encrypted = encrypt_value(plain)
        assert decrypt_value(encrypted) == plain

    def test_round_trip_empty_string(self):
        encrypted = encrypt_value("")
        assert decrypt_value(encrypted) == ""

    def test_different_encryptions_differ(self):
        """Fernet uses a nonce so same plaintext → different ciphertext."""
        a = encrypt_value("same")
        b = encrypt_value("same")
        assert a != b
        assert decrypt_value(a) == decrypt_value(b) == "same"

    def test_decrypt_with_wrong_key_raises(self, monkeypatch):
        encrypted = encrypt_value("secret")
        # Switch to a different key
        monkeypatch.setenv(
            "NOTIFICATION_ENCRYPTION_KEY", Fernet.generate_key().decode()
        )
        import app.encryption as enc_mod

        enc_mod._fernet = None
        with pytest.raises(InvalidToken):
            decrypt_value(encrypted)

    def test_decrypt_garbage_raises(self):
        with pytest.raises(InvalidToken):
            decrypt_value("not-valid-fernet-token")

    def test_missing_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("NOTIFICATION_ENCRYPTION_KEY", raising=False)
        import app.encryption as enc_mod

        enc_mod._fernet = None
        with pytest.raises(
            RuntimeError, match="NOTIFICATION_ENCRYPTION_KEY is not set"
        ):
            encrypt_value("test")
