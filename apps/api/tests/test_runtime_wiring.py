"""Lot 5: what the settings set in the administration change (spec §3.2)."""

from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import litellm
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.embeddings import LiteLLMEmbedder
from app.core import crypto
from app.core.config import get_settings
from app.db.models import AiCall, Organization
from app.services import credits
from app.services.tender_import import readers
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox
from tests.core.test_runtime import put

Factory = Callable[[], TestClient]


class Ok(BaseModel):
    ok: bool


def company(db: Session) -> Organization:
    org = Organization(siren="552100554", siret="55210055400013", name="Câblage Test")
    db.add(org)
    db.flush()
    return org


def test_an_ai_call_uses_the_task_model_and_the_key(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def completion(**kw: Any) -> SimpleNamespace:
        seen.update(kw)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ok": true}'), finish_reason="stop"
                )
            ],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
            _hidden_params={"response_cost": 0.0001},
        )

    monkeypatch.setattr(litellm, "completion", completion)
    put(db, "model.tender_scoring", "openrouter/cheap")
    put(db, "openrouter_api_key", secret=crypto.encrypt("sk-or-admin-1234", "openrouter_api_key"))
    org = company(db)
    result = llm.complete(
        db,
        org_id=org.id,
        task="tender_scoring",
        messages=[{"role": "user", "content": "x"}],
        response_model=Ok,
    )
    assert result.data.ok is True
    assert (seen["model"], seen["api_key"]) == ("openrouter/cheap", "sk-or-admin-1234")


def test_indexing_uses_the_key(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def embedding(**kw: Any) -> SimpleNamespace:
        seen.update(kw)
        return SimpleNamespace(
            data=[{"embedding": [0.0] * 4}], usage=SimpleNamespace(prompt_tokens=1)
        )

    monkeypatch.setattr(litellm, "embedding", embedding)
    put(db, "openrouter_api_key", secret=crypto.encrypt("sk-or-admin-5678", "openrouter_api_key"))
    LiteLLMEmbedder("openrouter/e", 4).embed(["a"])
    assert seen["api_key"] == "sk-or-admin-5678"


def test_without_any_key_litellm_reads_the_environment(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "")
    monkeypatch.setattr(
        litellm,
        "embedding",
        lambda **kw: seen.update(kw)
        or SimpleNamespace(data=[{"embedding": [0.0]}], usage=SimpleNamespace(prompt_tokens=1)),
    )
    LiteLLMEmbedder("openrouter/e", 1).embed(["a"])
    assert "api_key" not in seen


def test_the_budget_set_here_blocks(db: Session) -> None:
    org = company(db)
    db.add(AiCall(org_id=org.id, task="dce_extraction", model="m", cost_eur=Decimal("1.50")))
    db.flush()
    llm.ensure_budget(db, org.id)  # 1,50 € under the server's 50 €
    put(db, "ai_monthly_budget_eur_per_org", 1)
    with pytest.raises(llm.LlmBudgetExceeded):
        llm.ensure_budget(db, org.id)


def test_the_support_address_set_here_is_shown(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    put(db, "support_email", "aide@pilao.test")
    assert c.get("/auth/me").json()["support_email"] == "aide@pilao.test"
    assert credits.credits_exhausted_error(5, 3).message.endswith(
        "Contactez Pilao : aide@pilao.test."
    )


def test_the_feedback_address_set_here_receives_it(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "feedback_email", "")
    c = signed_in_client(make_client, outbox)
    put(db, "feedback_email", "avis@pilao.test")
    body = {"kind": "idea", "message": "Une idée", "page": "/tableau-de-bord"}
    assert c.post("/feedback", json=body).status_code == 201
    assert outbox.sent[-1].to == "avis@pilao.test"


def test_a_source_switched_off_here_is_not_imported(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ted_import_enabled", True)
    monkeypatch.setattr(get_settings(), "boamp_import_enabled", False)
    assert set(readers()) == {"ted"}
    put(db, "import.ted_enabled", False)
    put(db, "import.boamp_enabled", True)
    assert set(readers()) == {"boamp"}
