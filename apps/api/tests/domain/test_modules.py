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
    ]
    assert set(ACTION_BY_KEY) == {a.key for a in PAID_ACTIONS}
