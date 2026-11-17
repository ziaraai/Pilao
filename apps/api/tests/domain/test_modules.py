"""The registry of modules (lot 3, spec §2, §5.1)."""

from app.db.models import Organization
from app.modules import BY_KEY, DEFAULT_MODULES, MODULES, active_modules, has_module


def test_registry() -> None:
    keys = [m.key for m in MODULES]
    assert keys == ["veille", "reponse"] and len(set(keys)) == len(keys)
    assert DEFAULT_MODULES == ("veille", "reponse")
    assert BY_KEY["veille"].name == "Veille des annonces"
    assert BY_KEY["reponse"].name == "Réponse aux appels d'offres"
    assert BY_KEY["veille"].nav == ("Annonces",)
    assert BY_KEY["reponse"].nav == ("Dossiers", "Coffre-fort", "Base documentaire")


def test_unknown_key_ignored() -> None:
    org = Organization(siren="1", siret="1", name="x", modules=["reponse", "crm", "veille"])
    assert active_modules(org) == ["veille", "reponse"]
    assert has_module(org, "reponse") and not has_module(org, "crm")
    assert active_modules(Organization(siren="1", siret="1", name="x", modules=[])) == []


def test_paid_actions() -> None:
    from app.modules import ACTION_BY_KEY, PAID_ACTIONS

    assert [(a.key, a.name, a.default_credits, a.ai_task) for a in PAID_ACTIONS] == [
        ("dce_analysis", "Analyse du DCE", 2, "dce_extraction"),
        ("memoir_generation", "Rédaction du mémoire", 5, "memoir_generation"),
        ("chapter_regeneration", "Régénérer un chapitre", 1, "memoir_regeneration"),
        ("profile_prefill", "Pré-remplir le profil depuis vos documents", 1, "profile_extraction"),
        ("marker_fill", "Compléter une information", 0, "marker_fill"),
        ("price_read", "Lire un fichier de prix", 1, "price_read"),
        ("quote_draft", "Préparer un devis", 1, "quote_draft"),
    ]
    assert set(ACTION_BY_KEY) == {a.key for a in PAID_ACTIONS}


def test_marker_fill_is_a_free_paid_action() -> None:
    from app.domain.admin_watch import TASK_LABELS
    from app.modules import ACTION_BY_KEY, MODULE_OF_ACTION
    from app.platform_settings import MODEL_LABELS, SETTINGS, TASK_MODELS
    from app.services.credits import REFUNDED_JOBS

    assert ACTION_BY_KEY["marker_fill"].default_credits == 0
    assert MODULE_OF_ACTION["marker_fill"] == "reponse"
    assert TASK_MODELS["marker_fill"] == "llm_model_generation"
    assert MODEL_LABELS["marker_fill"] == "Compléter une information"
    assert "model.marker_fill" in {s.name for s in SETTINGS}
    assert TASK_LABELS["marker_fill"] == "Complétion d'une information"
    assert REFUNDED_JOBS["fill_marker"] == (
        "marker_fill",
        "Remboursé : la complétion n'a pas abouti.",
    )
