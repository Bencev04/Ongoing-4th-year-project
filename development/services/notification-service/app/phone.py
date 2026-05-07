"""E.164 phone number normalisation.

Handles Irish mobile formats (08x, 353-xxx) and international numbers.
Returns None for invalid/empty input.
"""

import re


def normalize_phone_e164(phone: str | None) -> str | None:
    """Normalise a phone number to E.164 format.

    Supports:
    - Irish mobile: 083 xxx xxxx, 083-xxx-xxxx, (083) xxx xxxx
    - Irish with country code: +353 83 xxx xxxx, 00353 83 xxx xxxx
    - Already E.164: +353831234567
    - International: +44 7911 123456

    Returns:
        E.164 string (e.g. ``+353831234567``) or ``None`` if invalid.
    """
    if not phone:
        return None

    # Strip whitespace, dashes, parentheses, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone)

    if not cleaned:
        return None

    # Already E.164
    if cleaned.startswith("+") and cleaned[1:].isdigit() and len(cleaned) >= 8:
        return cleaned

    # 00-prefixed international (e.g. 00353...)
    if cleaned.startswith("00") and cleaned[2:].isdigit():
        return f"+{cleaned[2:]}"

    # Irish local mobile starting with 08x
    if re.match(r"^08[3-9]\d{7}$", cleaned):
        return f"+353{cleaned[1:]}"

    # Irish number starting with 353 (missing +)
    if cleaned.startswith("353") and cleaned.isdigit() and len(cleaned) >= 10:
        return f"+{cleaned}"

    # Digits-only that looks like a valid number (10+ digits)
    if cleaned.isdigit() and len(cleaned) >= 10:
        return f"+{cleaned}"

    return None
