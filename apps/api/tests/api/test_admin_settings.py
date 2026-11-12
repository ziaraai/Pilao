"""Administration, lot 5: the settings screen — AI models and the OpenRouter key (spec §3)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.core import crypto, runtime
from app.core.config import get_settings
from app.db.models import AiCall, PlatformSetting, TenderImport
from app.domain.ai_catalogue import eur_per_million
from app.platform_settings import MODEL_LABELS
from app.services.admin import settings as settings_svc
from tests.api.helpers import signed_in_client
from tests.api.test_admin_accounts import admin, journal
from tests.conftest import FakeOpenRouter, FakeQueue, Outbox
from tests.core.test_runtime import put

Factory = Callable[[], TestClient]
GOOD_KEY = "sk-or-v1-good-0001abcd"


def answers(content: str) -> Callable[..., Any]:
    return lambda model, messages, max_tokens=None: (content, 12, 3, 0.0001)


@pytest.fixture
def trial_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "_call_provider", answers('{"ok": true}'))


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    for attr in ("llm_model_extraction", "llm_model_generation", "llm_model_vision"):
        monkeypatch.setattr(s, attr, "")
    monkeypatch.setattr(s, "llm_model_scoring", "openrouter/acme/small")
    monkeypatch.setattr(s, "llm_catalogue_prefix", "openrouter/")
    monkeypatch.setattr(s, "openrouter_api_key", "")


def test_state_lists_six_tasks_with_their_server_values(
    make_client: Factory, db: Session, server: None
) -> None:
    client, _, _ = admin(make_client, db)
    res = client.get("/admin/settings")
    assert res.status_code == 200, res.text
    body = res.json()
    assert [m["task"] for m in body["models"]] == list(MODEL_LABELS)
    assert all(m["source"] == "server" for m in body["models"])
    scoring = next(m for m in body["models"] if m["task"] == "tender_scoring")
    assert (scoring["label"], scoring["model"], scoring["model_name"]) == (
        "Note des annonces",
        "openrouter/acme/small",
        "Acme Small",
    )
    rate = get_settings().usd_eur_rate
    assert scoring["price_in_eur"] == eur_per_million(0.0000001, rate)
    assert scoring["in_catalogue"] is True and scoring["calls_30d"] == 0
    reading = next(m for m in body["models"] if m["task"] == "dce_extraction")
    assert reading["model"] == "" and reading["in_catalogue"] is None
    assert body["embedding_model"] == get_settings().embedding_model
    assert body["api_key"]["source"] == "none" and body["api_key"]["credit"] is None


def test_catalogue_for_a_task(
    make_client: Factory, db: Session, openrouter: FakeOpenRouter
) -> None:
    client, _, _ = admin(make_client, db)
    res = client.get("/admin/settings/catalogue", params={"task": "tender_scoring"})
    assert res.status_code == 200, res.text
    assert [m["id"] for m in res.json()] == ["acme/small", "acme/vision"]  # sorted by name
    assert res.json()[0]["context_length"] == 128000
    vision = client.get("/admin/settings/catalogue", params={"task": "compliance_reading"})
    assert [m["id"] for m in vision.json()] == ["acme/vision"]
    assert openrouter.model_reads == 1  # kept for an hour
    settings_svc.clear_catalogue_cache()
    client.get("/admin/settings/catalogue", params={"task": "tender_scoring"})
    assert openrouter.model_reads == 2
    settings_svc.clear_catalogue_cache()
    openrouter.down = True
    res = client.get("/admin/settings/catalogue", params={"task": "tender_scoring"})
    assert res.status_code == 503
    assert res.json()["error"]["message"] == (
        "Catalogue OpenRouter indisponible, réessayez dans un moment."
    )
    unknown = client.get("/admin/settings/catalogue", params={"task": "inconnue"})
    assert unknown.status_code == 404 and unknown.json()["error"]["message"] == "Tâche inconnue."


def test_a_model_is_tried_then_saved(
    make_client: Factory, db: Session, server: None, trial_ok: None
) -> None:
    client, _, _ = admin(make_client, db)
    res = client.put("/admin/settings/models/tender_scoring", json={"model_id": "acme/vision"})
    assert res.status_code == 200, res.text
    assert (res.json()["model"], res.json()["source"]) == ("openrouter/acme/vision", "admin")
    trial = db.scalars(select(AiCall).where(AiCall.task == "settings_check")).one()
    assert trial.org_id is None and trial.model == "openrouter/acme/vision"
    [line] = journal(db, "setting_changed")
    assert line.meta == {
        "setting": "model.tender_scoring",
        "label": "Note des annonces",
        "from": "openrouter/acme/small",
        "to": "openrouter/acme/vision",
    }
    assert runtime.model_for_task("tender_scoring") == "openrouter/acme/vision"


def test_a_failed_trial_saves_nothing(
    make_client: Factory, db: Session, server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "_call_provider", answers("Bonjour !"))
    client, _, _ = admin(make_client, db)
    res = client.put("/admin/settings/models/tender_scoring", json={"model_id": "acme/vision"})
    assert res.status_code == 422
    assert res.json()["error"]["message"] == (
        "Le modèle n'a pas répondu correctement : réponse illisible."
    )
    assert db.scalars(select(PlatformSetting)).all() == []
    assert journal(db, "setting_changed") == []


def test_a_model_unfit_for_the_task(
    make_client: Factory, db: Session, server: None, trial_ok: None, openrouter: FakeOpenRouter
) -> None:
    client, _, _ = admin(make_client, db)
    unfit = "Ce modèle ne convient pas à cette tâche."
    for task, model_id in [
        ("tender_scoring", "acme/small:free"),
        ("tender_scoring", "~acme/latest"),
        ("tender_scoring", "nope/x"),
        ("compliance_reading", "acme/small"),  # cannot read images
    ]:
        res = client.put(f"/admin/settings/models/{task}", json={"model_id": model_id})
        assert res.status_code == 422 and res.json()["error"]["message"] == unfit, model_id
    res = client.put("/admin/settings/models/inconnue", json={"model_id": "acme/small"})
    assert res.status_code == 404 and res.json()["error"]["message"] == "Tâche inconnue."
    settings_svc.clear_catalogue_cache()  # past the hour: OpenRouter is asked again
    openrouter.down = True
    res = client.put("/admin/settings/models/tender_scoring", json={"model_id": "acme/small"})
    assert res.status_code == 503
    assert db.scalars(select(PlatformSetting)).all() == []


def test_back_to_the_server_value(
    make_client: Factory, db: Session, server: None, trial_ok: None
) -> None:
    client, _, _ = admin(make_client, db)
    client.put("/admin/settings/models/tender_scoring", json={"model_id": "acme/vision"})
    assert client.delete("/admin/settings/models/tender_scoring").status_code == 204
    assert runtime.model_for_task("tender_scoring") == "openrouter/acme/small"
    [line] = journal(db, "setting_reset")
    assert line.meta == {
        "setting": "model.tender_scoring",
        "label": "Note des annonces",
        "from": "openrouter/acme/vision",
        "to": "openrouter/acme/small",
    }
    assert client.delete("/admin/settings/models/tender_scoring").status_code == 204  # idle
    # the server has no model for this task: the value set here stays
    client.put("/admin/settings/models/dce_extraction", json={"model_id": "acme/small"})
    res = client.delete("/admin/settings/models/dce_extraction")
    assert res.status_code == 409
    assert res.json()["error"]["message"] == "Le serveur n'a pas de valeur pour ce réglage."
    assert runtime.model_for_task("dce_extraction") == "openrouter/acme/small"


def test_the_key_is_checked_stored_encrypted_never_returned(
    make_client: Factory, db: Session, server: None, openrouter: FakeOpenRouter
) -> None:
    client, _, _ = admin(make_client, db)
    res = client.put("/admin/settings/api-key", json={"key": f"  {GOOD_KEY} "})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["source"], body["last4"], body["unreadable"]) == ("admin", "abcd", False)
    assert body["credit"] == {"total_usd": 5.0, "used_usd": 1.32}
    row = db.get_one(PlatformSetting, "openrouter_api_key")
    assert row.secret and GOOD_KEY not in row.secret
    assert crypto.decrypt(row.secret, "openrouter_api_key") == GOOD_KEY
    assert GOOD_KEY not in res.text and GOOD_KEY not in client.get("/admin/settings").text
    [line] = journal(db, "api_key_replaced")
    assert line.meta == {"last4": "abcd"}
    assert runtime.api_key() == GOOD_KEY

    refused = client.put("/admin/settings/api-key", json={"key": "sk-or-v1-bad-9999"})
    assert refused.status_code == 422
    assert refused.json()["error"]["message"] == "Clé refusée par OpenRouter."
    assert client.put("/admin/settings/api-key", json={"key": "   "}).status_code == 422
    openrouter.down = True
    down = client.put("/admin/settings/api-key", json={"key": "sk-or-v1-good-other"})
    assert down.status_code == 503
    assert down.json()["error"]["message"] == (
        "OpenRouter ne répond pas : la clé n'est pas vérifiée, rien n'est changé."
    )
    assert runtime.api_key() == GOOD_KEY  # unchanged by the refusals


def test_back_to_the_server_key(
    make_client: Factory, db: Session, server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = admin(make_client, db)
    client.put("/admin/settings/api-key", json={"key": GOOD_KEY})
    res = client.delete("/admin/settings/api-key")
    assert res.status_code == 409
    assert res.json()["error"]["message"] == (
        "Le serveur n'a pas de clé : remplacez la clé plutôt que de la retirer."
    )
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "sk-srv-0000xyz9")
    assert client.delete("/admin/settings/api-key").status_code == 204
    key = client.get("/admin/settings").json()["api_key"]
    assert (key["source"], key["last4"], key["server_key"]) == ("server", "xyz9", True)
    assert len(journal(db, "api_key_reset")) == 1


def test_unreadable_key_on_the_screen(
    make_client: Factory, db: Session, server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "sk-srv-0000xyz9")
    client, _, _ = admin(make_client, db)
    put(db, "openrouter_api_key", secret="pas-un-jeton")
    res = client.get("/admin/settings")
    assert res.status_code == 200
    key = res.json()["api_key"]
    assert (key["unreadable"], key["source"], key["last4"]) == (True, "server", "xyz9")


def test_company_session_refused(make_client: Factory, outbox: Outbox) -> None:
    company = signed_in_client(make_client, outbox)
    for method, path in [
        ("get", "/admin/settings"),
        ("get", "/admin/settings/catalogue?task=tender_scoring"),
        ("put", "/admin/settings/models/tender_scoring"),
        ("delete", "/admin/settings/models/tender_scoring"),
        ("put", "/admin/settings/api-key"),
        ("delete", "/admin/settings/api-key"),
    ]:
        assert company.request(method, path, json={}).status_code == 401, path


# ---------- imports, general settings, « À surveiller » (task 5) ------------------------------


def test_switch_an_import_off_and_on(
    make_client: Factory, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.tender_import import readers

    monkeypatch.setattr(get_settings(), "boamp_import_enabled", True)
    client, _, _ = admin(make_client, db)
    res = client.put("/admin/settings/imports/boamp", json={"enabled": False})
    assert res.status_code == 200, res.text
    assert (res.json()["enabled"], res.json()["origin"]) == (False, "admin")
    [line] = journal(db, "setting_changed")
    assert line.meta == {
        "setting": "import.boamp_enabled",
        "label": "Import BOAMP",
        "from": True,
        "to": False,
    }
    assert "boamp" not in readers()  # the scheduled pass skips it
    assert client.delete("/admin/settings/imports/boamp").status_code == 204
    assert "boamp" in readers()
    unknown = client.put("/admin/settings/imports/sirene", json={"enabled": True})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["message"] == "Source inconnue."


def test_import_now(
    make_client: Factory, db: Session, queue: FakeQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ted_import_enabled", True)
    client, _, _ = admin(make_client, db)
    res = client.post("/admin/settings/imports/ted/run")
    assert res.status_code == 202, res.text
    assert queue.pending_imports == ["ted"]
    [line] = journal(db, "import_started")
    assert line.meta == {"source": "ted"}

    now = datetime.now(UTC)
    running = TenderImport(source="ted", status="running", since=now.date())
    db.add(running)
    db.flush()
    running.created_at = now - timedelta(minutes=10)
    db.commit()
    busy = client.post("/admin/settings/imports/ted/run")
    assert busy.status_code == 409
    assert busy.json()["error"]["message"] == "Un passage est déjà en cours."
    running.created_at = now - timedelta(hours=2)  # a dead pass (Review Focus 4)
    db.commit()
    assert client.post("/admin/settings/imports/ted/run").status_code == 202

    queue.down = True
    down = client.post("/admin/settings/imports/ted/run")
    assert down.status_code == 503
    assert down.json()["error"]["message"] == "File d'attente indisponible."
    queue.down = False
    client.put("/admin/settings/imports/ted", json={"enabled": False})
    off = client.post("/admin/settings/imports/ted/run")
    assert off.status_code == 409
    assert off.json()["error"]["message"] == "Activez d'abord l'import TED."


def test_general_settings(make_client: Factory, db: Session) -> None:
    client, _, _ = admin(make_client, db)
    url = "/admin/settings/general"
    for value in (1, 10_000):
        res = client.put(f"{url}/ai_monthly_budget_eur_per_org", json={"value": value})
        assert res.status_code == 200, res.text
        assert (res.json()["value"], res.json()["source"]) == (value, "admin")
    for value in (0, 10_001, "abc", 2.5, True):
        res = client.put(f"{url}/ai_monthly_budget_eur_per_org", json={"value": value})
        assert res.status_code == 422, value
    assert client.put(f"{url}/support_email", json={"value": "pas une adresse"}).status_code == 422
    assert client.put(f"{url}/support_email", json={"value": ""}).json()["value"] == ""
    res = client.put(f"{url}/support_email", json={"value": " aide@example.fr "})
    assert res.json()["value"] == "aide@example.fr"
    assert runtime.effective("support_email") == "aide@example.fr"
    for name in ("inconnu", "import.ted_enabled", "openrouter_api_key"):
        res = client.put(f"{url}/{name}", json={"value": 1})
        assert res.status_code == 404 and res.json()["error"]["message"] == "Réglage inconnu."
    assert client.delete(f"{url}/support_email").status_code == 204
    assert runtime.source("support_email") == "server"
    assert len(journal(db, "setting_changed")) == 4 and len(journal(db, "setting_reset")) == 1


def test_last_pass_of_each_source(make_client: Factory, db: Session) -> None:
    now = datetime.now(UTC)
    db.add(TenderImport(source="ted", status="done", since=now.date(), created=4, updated=2))
    db.commit()
    client, _, _ = admin(make_client, db)
    imports = {i["source"]: i for i in client.get("/admin/settings").json()["imports"]}
    assert imports["ted"]["last"]["status"] == "done"
    assert (imports["ted"]["last"]["created"], imports["ted"]["last"]["updated"]) == (4, 2)
    assert imports["boamp"]["last"] is None and imports["ted"]["label"] == "Import TED"


def test_watch_lines(
    make_client: Factory,
    db: Session,
    openrouter: FakeOpenRouter,
    monkeypatch: pytest.MonkeyPatch,
    server: None,
) -> None:
    client, _, _ = admin(make_client, db)

    def settings_lines() -> list[tuple[str, str]]:
        watch = client.get("/admin/overview").json()["watch"]
        return [(w["level"], w["title"]) for w in watch if w["kind"] == "settings"]

    assert settings_lines() == []
    put(db, "openrouter_api_key", secret="pas-un-jeton")
    monkeypatch.setattr(get_settings(), "llm_model_scoring", "openrouter/acme/gone")
    assert settings_lines() == [
        ("red", "La clé OpenRouter enregistrée est illisible"),
        ("amber", "Note des annonces : modèle retiré du catalogue OpenRouter"),
    ]
    settings_svc.clear_catalogue_cache()
    openrouter.down = True  # unknown catalogue: no line about the models, never an error
    assert settings_lines() == [("red", "La clé OpenRouter enregistrée est illisible")]


def test_company_session_refused_on_imports_and_general(
    make_client: Factory, outbox: Outbox
) -> None:
    company = signed_in_client(make_client, outbox)
    for method, path in [
        ("put", "/admin/settings/imports/ted"),
        ("delete", "/admin/settings/imports/ted"),
        ("post", "/admin/settings/imports/ted/run"),
        ("put", "/admin/settings/general/support_email"),
        ("delete", "/admin/settings/general/support_email"),
    ]:
        assert company.request(method, path, json={}).status_code == 401, path
