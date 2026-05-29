import re


def normalize_ar_phone(phone: str) -> str:
    """
    Normalize an Argentine mobile phone to +549XXXXXXXXXX (WhatsApp format).

    Handles:
      +54XXXXXXXXXX  → +549XXXXXXXXXX  (missing mobile 9)
      549XXXXXXXXXX  → +549XXXXXXXXXX  (missing + prefix)
      54XXXXXXXXXX   → +549XXXXXXXXXX  (missing both)

    Non-Argentine numbers (+1..., +55..., etc.) get only basic + normalization.
    Blank values are returned unchanged.
    """
    if not phone:
        return phone

    # Strip spaces, dashes, dots, parentheses
    cleaned = re.sub(r'[\s\-\(\).]', '', phone.strip())

    # Ensure leading +
    if cleaned.startswith('00'):
        cleaned = '+' + cleaned[2:]
    elif not cleaned.startswith('+'):
        cleaned = '+' + cleaned

    # Only transform Argentine numbers
    if cleaned.startswith('+54'):
        after = cleaned[3:]   # digits after country code
        if after and after[0] != '9':
            cleaned = '+549' + after

    return cleaned


def ar_phone_variants(phone: str) -> list:
    """
    Return both +549X and +54X variants of an Argentine number for fuzzy DB lookup.
    Used to match leads/conversations regardless of whether the 9 is present.
    """
    variants = [phone]
    if phone.startswith('+549'):
        variants.append('+54' + phone[4:])
    elif phone.startswith('+54') and len(phone) > 3:
        variants.append('+549' + phone[3:])
    return variants
