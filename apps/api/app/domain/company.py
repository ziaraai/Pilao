"""Facts derived from official identifiers (never guessed)."""


def vat_number(siren: str) -> str:
    """French intra-community VAT number: FR + key + SIREN, key = (12 + 3 × (SIREN mod 97)) mod 97."""
    key = (12 + 3 * (int(siren) % 97)) % 97
    return f"FR{key:02d}{siren}"
