"""The modules of Pilao (lot 3, ADR-041): blocks of the product a company has or not.

A module is declared here once: its key, its name and what it contains. A company's active
modules are ``organizations.modules``; the routes of a module are guarded by
``core.deps.require_module`` and its background work skips the companies without it. Adding a
module later (a CRM, stock) means writing its code and adding one entry to ``MODULES``.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import Organization


@dataclass(frozen=True)
class PaidAction:
    """An action that costs credits (lot 4). Its price is set in the administration; this is
    the starting one. ``ai_task``: the ``ai_calls.task`` of its AI calls (its real cost)."""

    key: str
    name: str
    default_credits: int
    ai_task: str


@dataclass(frozen=True)
class Module:
    key: str
    name: str
    description: str
    contents: tuple[str, ...]  # what it brings, shown in the administration
    nav: tuple[str, ...]  # its entries in the company's menu
    actions: tuple[PaidAction, ...] = ()  # what it charges credits for (lot 4)


MODULES: tuple[Module, ...] = (
    Module(
        key="veille",
        name="Veille des annonces",
        description="Les annonces publiques qui correspondent à l'entreprise, chaque matin.",
        contents=(
            "les annonces BOAMP et TED filtrées pour l'entreprise et notées par l'IA",
            "les alertes du matin",
        ),
        nav=("Annonces",),
    ),
    Module(
        key="reponse",
        name="Réponse aux appels d'offres",
        description="Du DCE déposé au dossier prêt à relire : analyse, mémoire, documents.",
        contents=(
            "les dossiers",
            "le dépôt et l'analyse du DCE",
            "le mémoire technique",
            "le DC1/DC2 et les exports",
            "le coffre-fort et ses rappels",
            "la base documentaire",
        ),
        nav=("Dossiers", "Coffre-fort", "Base documentaire"),
        actions=(
            PaidAction("dce_analysis", "Analyse du DCE", 2, "dce_extraction"),
            PaidAction("memoir_generation", "Rédaction du mémoire", 5, "memoir_generation"),
            PaidAction("chapter_regeneration", "Régénérer un chapitre", 1, "memoir_regeneration"),
            PaidAction(
                "profile_prefill",
                "Pré-remplir le profil depuis vos documents",
                1,
                "profile_extraction",
            ),
        ),
    ),
)
DEFAULT_MODULES: tuple[str, ...] = tuple(m.key for m in MODULES)
BY_KEY: dict[str, Module] = {m.key: m for m in MODULES}
PAID_ACTIONS: tuple[PaidAction, ...] = tuple(a for m in MODULES for a in m.actions)
ACTION_BY_KEY: dict[str, PaidAction] = {a.key: a for a in PAID_ACTIONS}
MODULE_OF_ACTION: dict[str, str] = {a.key: m.key for m in MODULES for a in m.actions}


def active_modules(org: Organization) -> list[str]:
    """The company's modules known to this code, in the registry's order."""
    present = set(org.modules or ())
    return [m.key for m in MODULES if m.key in present]


def has_module(org: Organization, key: str) -> bool:
    return key in active_modules(org)


def has_paid_actions(modules: Iterable[str] | None) -> bool:
    """Lot 4: whether one of a company's modules (``org.modules``) has a paid action. Without
    any, its credits mean nothing to it: no balance shown, no « plus de crédits » alert."""
    present = set(modules or ())
    return any(m.actions for m in MODULES if m.key in present)


def module_disabled_error() -> ApiError:
    support = get_settings().support_email.strip()
    contact = f"Contactez Pilao : {support}." if support else "Contactez Pilao."
    return ApiError(
        403,
        "module_disabled",
        f"Ce module n'est pas activé pour votre entreprise. {contact}",
    )
