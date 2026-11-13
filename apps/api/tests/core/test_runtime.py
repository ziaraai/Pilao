"""Lot 5: the value of a setting is the administration's, else the server's (spec §2, §3.2)."""

import pytest
from sqlalchemy.orm import Session

from app.core import crypto, runtime
from app.core.config import get_settings
from app.db.models import PlatformSetting
from app.platform_settings import BY_NAME, SETTINGS, TASK_MODELS


def put(db: Session, key: str, value: object = None, secret: str | None = None) -> None:
    db.add(PlatformSetting(key=key, value=value, secret=secret, secret_last4="1234"))
    db.flush()
    runtime.invalidate()


def test_admin_value_wins_then_server_value(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "support_email", "serveur@pilao.test")
    assert runtime.effective("support_email") == "serveur@pilao.test"
    assert runtime.source("support_email") == "server"
    put(db, "support_email", "aide@pilao.test")
    assert runtime.effective("support_email") == "aide@pilao.test"
    assert runtime.source("support_email") == "admin"
    db.get_one(PlatformSetting, "support_email").value = ""  # « aucune »
    db.flush()
    runtime.invalidate()
    assert runtime.effective("support_email") == ""


def test_model_for_task_falls_back_to_its_group(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "llm_model_scoring", "srv/scoring")
    assert runtime.model_for_task("tender_scoring") == "srv/scoring"
    put(db, "model.tender_scoring", "openrouter/x")
    assert runtime.model_for_task("tender_scoring") == "openrouter/x"


def test_snapshot_is_reread_after_30_seconds(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    runtime.invalidate()
    assert runtime.source("feedback_email") == "server"  # snapshot taken at 1000
    db.add(PlatformSetting(key="feedback_email", value="avis@pilao.test"))
    db.flush()
    clock[0] = 1029.0
    assert runtime.source("feedback_email") == "server"  # not re-read yet
    clock[0] = 1031.0
    assert runtime.effective("feedback_email") == "avis@pilao.test"
    db.get_one(PlatformSetting, "feedback_email").value = "autre@pilao.test"
    db.flush()
    runtime.invalidate()  # the process that writes sees it at once
    assert runtime.effective("feedback_email") == "autre@pilao.test"


def test_api_key_admin_then_server_then_none(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "")
    assert runtime.api_key() is None
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "sk-srv")
    assert runtime.api_key() == "sk-srv"
    put(db, "openrouter_api_key", secret=crypto.encrypt("sk-or-admin-1234", "openrouter_api_key"))
    assert runtime.api_key() == "sk-or-admin-1234"
    assert runtime.snapshot().key_last4 == "1234"


def test_unreadable_key_falls_back_to_server(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "sk-srv")
    put(db, "openrouter_api_key", secret="pas-un-jeton")
    assert runtime.snapshot().key_unreadable is True
    assert runtime.snapshot().key is None
    assert runtime.api_key() == "sk-srv"


def test_registry() -> None:
    names = [s.name for s in SETTINGS]
    assert len(names) == 13 and len(set(names)) == 13
    assert [s.kind for s in SETTINGS].count("model") == 6
    assert {f"model.{task}" for task in TASK_MODELS} <= set(names)
    budget = BY_NAME["ai_monthly_budget_eur_per_org"]
    assert (budget.kind, budget.minimum, budget.maximum) == ("int", 1, 10_000)
    assert BY_NAME["model.tender_scoring"].label == "Note des annonces"
    assert BY_NAME["import.boamp_enabled"].label == "Import BOAMP"
    robot = BY_NAME["dce_robot.enabled"]
    assert (robot.kind, robot.label) == ("bool", "Robot de récupération des DCE")
