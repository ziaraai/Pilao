"""French places: the department of a postal code (notices, company registry)."""

import re


def department_of(postal_code: str | None) -> str | None:
    """42000 → 42, 20090 → 2A, 20200 → 2B, 97400 → 974; None for what is no department."""
    code = (postal_code or "").strip().replace(" ", "")
    if not re.fullmatch(r"\d{5}", code):
        return None
    if code.startswith("97"):
        return code[:3] if code[2] in "12346" else None  # 971–976; 975 is not a department
    if code.startswith("98"):
        return None  # Monaco, overseas collectivities
    if code.startswith("20"):
        return "2A" if code[:3] in ("200", "201") else "2B"
    return code[:2]
