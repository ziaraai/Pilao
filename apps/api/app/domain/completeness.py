"""Profile completeness (US-1.3 CA3): a percentage and the list of what is missing."""

from dataclasses import dataclass

# (key, weight, French label shown to the user)
CRITERIA: tuple[tuple[str, int, str], ...] = (
    ("identity", 10, "Identité de l'entreprise (adresse, code NAF)"),
    ("trades", 15, "Au moins un métier"),
    ("watch", 15, "Codes CPV ou mots-clés de veille"),
    ("departments", 10, "Départements d'intervention"),
    ("revenue", 10, "Chiffre d'affaires des 3 derniers exercices"),
    ("human_resources", 10, "Moyens humains"),
    ("equipment", 10, "Moyens matériels"),
    ("certifications", 5, "Certifications"),
    ("references", 15, "Au moins 3 références de chantiers"),
)


@dataclass(frozen=True)
class Facts:
    has_address: bool
    has_naf: bool
    trades: int
    cpv_or_keywords: int
    departments: int
    revenue_years: int
    human_resources: int
    equipment: int
    certifications: int
    references: int


@dataclass(frozen=True)
class Completeness:
    pct: int
    missing: list[str]
    missing_keys: list[str]  # the same items, as CRITERIA keys (the profile tab to open)


# Asked only of a company with the « Veille » module: they only steer the watch (lot 3).
WATCH_ONLY = ("watch", "departments")


def compute(f: Facts, *, watch: bool = True) -> Completeness:
    """``watch``: the company has « Veille »; without it, the watch settings count as given."""
    ok = {
        "identity": f.has_address and f.has_naf,
        "trades": f.trades > 0,
        "watch": f.cpv_or_keywords > 0,
        "departments": f.departments > 0,
        "revenue": f.revenue_years >= 3,
        "human_resources": f.human_resources > 0,
        "equipment": f.equipment > 0,
        "certifications": f.certifications > 0,
        "references": f.references >= 3,
    }
    if not watch:
        ok.update(dict.fromkeys(WATCH_ONLY, True))
    pct = sum(w for k, w, _ in CRITERIA if ok[k])
    return Completeness(
        pct=pct,
        missing=[label for k, _, label in CRITERIA if not ok[k]],
        missing_keys=[k for k, _, _ in CRITERIA if not ok[k]],
    )
