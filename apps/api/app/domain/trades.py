"""Business trades offered at sign-up (US-1.2) and the CPV codes / keywords they pre-select.

Source: data/cpv-nettoyage.md. The CPV codes there are flagged "à vérifier" against the
official nomenclature before going to production.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Trade:
    code: str
    label: str
    cpv_codes: tuple[str, ...]
    keywords: tuple[str, ...] = ()


TRADES: dict[str, Trade] = {
    t.code: t
    for t in (
        Trade(
            "nettoyage_locaux",
            "Nettoyage de locaux (bureaux, écoles, bâtiments)",
            ("90910000", "90911000", "90911200", "90919000", "90919200", "90919300"),
            ("nettoyage", "entretien des locaux", "propreté"),
        ),
        Trade("vitrerie", "Vitrerie", ("90911300",), ("vitrerie",)),
        Trade(
            "remise_en_etat",
            "Remise en état / nettoyage après chantier",
            ("90911200",),
            ("fin de chantier", "remise en état"),
        ),
        Trade(
            "hygiene",
            "Hygiène, désinfection",
            ("90920000", "90921000"),
            ("bionettoyage", "désinfection"),
        ),
        Trade(
            "nettoyage_exterieur",
            "Nettoyage extérieur, parkings, graffitis",
            ("90610000", "90914000", "90690000"),
        ),
    )
}


def defaults_for(trade_codes: list[str]) -> tuple[list[str], list[str]]:
    """CPV codes and keywords for the given trades, deduplicated, order preserved."""
    cpv: dict[str, None] = {}
    kw: dict[str, None] = {}
    for code in trade_codes:
        trade = TRADES[code]
        cpv.update(dict.fromkeys(trade.cpv_codes))
        kw.update(dict.fromkeys(trade.keywords))
    return list(cpv), list(kw)
