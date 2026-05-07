"""Tests for phone number normalisation to E.164 format."""

from app.phone import normalize_phone_e164


class TestNormalizePhoneE164:
    """Full coverage for Irish and international phone normalisation."""

    # ── Irish mobile (08x → +353 8x) ──────────────────────────────

    def test_irish_mobile_0831234567(self):
        assert normalize_phone_e164("0831234567") == "+353831234567"

    def test_irish_mobile_with_spaces(self):
        assert normalize_phone_e164("083 123 4567") == "+353831234567"

    def test_irish_mobile_with_dashes(self):
        assert normalize_phone_e164("083-123-4567") == "+353831234567"

    def test_irish_mobile_with_parens(self):
        assert normalize_phone_e164("(083) 1234567") == "+353831234567"

    def test_irish_mobile_085(self):
        assert normalize_phone_e164("0851234567") == "+353851234567"

    def test_irish_mobile_086(self):
        assert normalize_phone_e164("0861234567") == "+353861234567"

    def test_irish_mobile_087(self):
        assert normalize_phone_e164("0871234567") == "+353871234567"

    def test_irish_mobile_089(self):
        assert normalize_phone_e164("0891234567") == "+353891234567"

    # ── Already in +353 format ────────────────────────────────────

    def test_irish_with_country_code(self):
        assert normalize_phone_e164("+353831234567") == "+353831234567"

    def test_irish_with_country_code_spaces(self):
        assert normalize_phone_e164("+353 83 123 4567") == "+353831234567"

    # ── International formats ─────────────────────────────────────

    def test_uk_mobile(self):
        assert normalize_phone_e164("+447911123456") == "+447911123456"

    def test_us_mobile(self):
        assert normalize_phone_e164("+12025551234") == "+12025551234"

    def test_international_00_prefix(self):
        result = normalize_phone_e164("00353831234567")
        assert result == "+353831234567"

    # ── Edge / invalid cases ──────────────────────────────────────

    def test_empty_string_returns_none(self):
        assert normalize_phone_e164("") is None

    def test_none_returns_none(self):
        assert normalize_phone_e164(None) is None

    def test_short_number_returns_none(self):
        assert normalize_phone_e164("123") is None

    def test_letters_only_returns_none(self):
        assert normalize_phone_e164("abcdefghij") is None

    def test_mixed_letters_and_digits_too_short(self):
        assert normalize_phone_e164("abc123") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_phone_e164("   ") is None

    # ── Bare digits (≥ 10 digits treat as-is with +) ─────────────────

    def test_bare_10_digits(self):
        """10+ bare digits that don't match Irish pattern get + prefix."""
        result = normalize_phone_e164("1234567890")
        assert result == "+1234567890"

    def test_bare_7_digits_returns_none(self):
        """Bare 7-digit number is too short for the >= 10 check."""
        assert normalize_phone_e164("1234567") is None

    def test_bare_9_digits_returns_none(self):
        """9 digits is below the 10-digit threshold."""
        assert normalize_phone_e164("123456789") is None
