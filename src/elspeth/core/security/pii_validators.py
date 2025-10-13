"""Australian PII checksum validators and Luhn algorithm.

This module provides validation functions for Australian government identifiers:
- TFN (Tax File Number) - 8-9 digits with checksum
- ABN (Australian Business Number) - 11 digits with checksum
- ACN (Australian Company Number) - 9 digits with checksum
- Medicare Number - 10 digits with checksum
- Credit Card (Luhn algorithm)
- BSB (Bank-State-Branch) - 6 digits, format validation only

Reference:
- ABN: https://abr.business.gov.au/Help/AbnFormat
- TFN: ATO specification
- Medicare: Services Australia specification
"""

from __future__ import annotations


def validate_tfn(tfn_str: str) -> bool:
    """Validate Australian Tax File Number (TFN) using checksum algorithm.

    TFN is 8-9 digits. Checksum algorithm:
    weights = [1, 4, 3, 7, 5, 8, 6, 9, 10]
    sum(digit[i] * weight[i]) % 11 == 0

    Args:
        tfn_str: TFN string (digits only, 8-9 chars)

    Returns:
        True if valid TFN checksum, False otherwise
    """
    # Remove all non-digits
    digits = ''.join(c for c in tfn_str if c.isdigit())

    if len(digits) not in (8, 9):
        return False

    # Pad to 9 digits if needed
    if len(digits) == 8:
        digits = '0' + digits

    weights = [1, 4, 3, 7, 5, 8, 6, 9, 10]
    total = sum(int(digits[i]) * weights[i] for i in range(9))

    return total % 11 == 0


def validate_abn(abn_str: str) -> bool:
    """Validate Australian Business Number (ABN) using checksum algorithm.

    ABN is 11 digits. Checksum algorithm:
    1. Subtract 1 from first digit
    2. weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    3. sum(digit[i] * weight[i]) % 89 == 0

    Args:
        abn_str: ABN string (digits only, 11 chars)

    Returns:
        True if valid ABN checksum, False otherwise
    """
    # Remove all non-digits
    digits = ''.join(c for c in abn_str if c.isdigit())

    if len(digits) != 11:
        return False

    # Subtract 1 from first digit
    first_digit = int(digits[0]) - 1
    if first_digit < 0:
        return False

    weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    total = first_digit * weights[0]
    total += sum(int(digits[i]) * weights[i] for i in range(1, 11))

    return total % 89 == 0


def validate_acn(acn_str: str) -> bool:
    """Validate Australian Company Number (ACN) using checksum algorithm.

    ACN is 9 digits. Checksum algorithm:
    weights = [8, 7, 6, 5, 4, 3, 2, 1]
    complement = 10 - (sum(digit[i] * weight[i]) % 10)
    check_digit = complement % 10
    digit[8] == check_digit

    Args:
        acn_str: ACN string (digits only, 9 chars)

    Returns:
        True if valid ACN checksum, False otherwise
    """
    # Remove all non-digits
    digits = ''.join(c for c in acn_str if c.isdigit())

    if len(digits) != 9:
        return False

    weights = [8, 7, 6, 5, 4, 3, 2, 1]
    total = sum(int(digits[i]) * weights[i] for i in range(8))

    complement = 10 - (total % 10)
    check_digit = complement % 10

    return int(digits[8]) == check_digit


def validate_medicare(medicare_str: str) -> bool:
    """Validate Australian Medicare Number using checksum algorithm.

    Medicare is 10 digits (ignoring optional IRN reference).
    Checksum algorithm:
    weights = [1, 3, 7, 9, 1, 3, 7, 9]
    sum(digit[i] * weight[i]) % 10 == check_digit (digit[8])

    Args:
        medicare_str: Medicare string (first 10 digits only)

    Returns:
        True if valid Medicare checksum, False otherwise
    """
    # Remove all non-digits
    digits = ''.join(c for c in medicare_str if c.isdigit())

    # Medicare can be 10 or 11 digits (11th is IRN)
    if len(digits) not in (10, 11):
        return False

    # Use first 10 digits for validation
    digits = digits[:10]

    # First digit must be 2-6 (card color indicator)
    if int(digits[0]) not in (2, 3, 4, 5, 6):
        return False

    weights = [1, 3, 7, 9, 1, 3, 7, 9]
    total = sum(int(digits[i]) * weights[i] for i in range(8))

    check_digit = total % 10

    return int(digits[8]) == check_digit


def validate_luhn(card_str: str) -> bool:
    """Validate credit card number using Luhn algorithm (mod 10).

    Args:
        card_str: Credit card number (digits only, 13-19 chars)

    Returns:
        True if passes Luhn check, False otherwise
    """
    # Remove all non-digits
    digits = ''.join(c for c in card_str if c.isdigit())

    if not (13 <= len(digits) <= 19):
        return False

    # Luhn algorithm
    total = 0
    reverse_digits = digits[::-1]

    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:  # Every second digit from right
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return total % 10 == 0


def validate_bsb(bsb_str: str) -> bool:
    """Validate BSB (Bank-State-Branch) format.

    BSB is 6 digits, often formatted as XXX-XXX.
    No checksum validation, just format check.

    Args:
        bsb_str: BSB string

    Returns:
        True if valid format (6 digits), False otherwise
    """
    # Remove all non-digits
    digits = ''.join(c for c in bsb_str if c.isdigit())

    return len(digits) == 6


def canonicalize_identifier(value: str) -> str:
    """Canonicalize identifier by removing all non-alphanumeric characters.

    Args:
        value: Raw identifier string

    Returns:
        Canonicalized string (digits/letters only, uppercase)
    """
    return ''.join(c.upper() for c in value if c.isalnum())
