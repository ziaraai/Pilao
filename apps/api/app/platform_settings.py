"""The settings the operator can change from the administration (lot 5, ADR-044).

Each one has a name, a French label, a kind and its server's value, read from ``Settings``
(``infra/server/app.env`` and ``secrets.env``). The value in use is the administration's when
there is one (``platform_settings``), else the server's: see ``app.core.runtime``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings

# AI task -> the Settings attribute holding its server model (ADR-005)
TASK_MODELS = {
    "dce_extraction": "llm_model_extraction",
    "memoir_generation": "llm_model_generation",
    "memoir_regeneration": "llm_model_generation",  # a new version of one chapter (lot 4)
    "profile_extraction": "llm_model_extraction",
    "tender_scoring": "llm_model_scoring",
    "compliance_reading": "llm_model_vision",
}
# The screen's labels of the tasks (not the AI costs' labels, admin_watch.TASK_LABELS)
MODEL_LABELS = {
    "dce_extraction": "Lecture du DCE",
    "memoir_generation": "Rédaction du mémoire",
    "memoir_regeneration": "Régénération d'un chapitre",
    "profile_extraction": "Pré-remplissage du profil",
    "tender_scoring": "Note des annonces",
    "compliance_reading": "Lecture des attestations",
}

Kind = Literal["model", "secret", "bool", "int", "email"]


@dataclass(frozen=True)
class SettingDef:
    name: str
    label: str
    kind: Kind
    server: Callable[[Settings], Any]
    task: str | None = None
    minimum: int | None = None
    maximum: int | None = None


def _attr(name: str) -> Callable[[Settings], Any]:
    return lambda s: getattr(s, name)


SETTINGS: tuple[SettingDef, ...] = (
    *(
        SettingDef(f"model.{task}", label, "model", _attr(TASK_MODELS[task]), task=task)
        for task, label in MODEL_LABELS.items()
    ),
    SettingDef("openrouter_api_key", "Clé OpenRouter", "secret", _attr("openrouter_api_key")),
    SettingDef("import.ted_enabled", "Import TED", "bool", _attr("ted_import_enabled")),
    SettingDef("import.boamp_enabled", "Import BOAMP", "bool", _attr("boamp_import_enabled")),
    SettingDef(
        "ai_monthly_budget_eur_per_org",
        "Budget d'IA par entreprise et par mois",
        "int",
        _attr("ai_monthly_budget_eur_per_org"),
        minimum=1,
        maximum=10_000,
    ),
    SettingDef("support_email", "Adresse de support", "email", _attr("support_email")),
    SettingDef("feedback_email", "Adresse des avis des testeurs", "email", _attr("feedback_email")),
)
BY_NAME: dict[str, SettingDef] = {s.name: s for s in SETTINGS}
GENERAL = ("ai_monthly_budget_eur_per_org", "support_email", "feedback_email")
IMPORTS = {"ted": "import.ted_enabled", "boamp": "import.boamp_enabled"}
