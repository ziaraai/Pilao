"""Lot 5: a model is tried before it is saved (spec §3.3)."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.db.models import AiCall


def answering(content: str) -> Any:
    def call(
        model: str, messages: list[dict[str, Any]], max_tokens: int | None = None, **_: Any
    ) -> Any:
        assert '{"ok": true}' in messages[0]["content"]
        return content, 12, 3, 0.0001

    return call


def test_a_model_that_answers(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "_call_provider", answering('{"ok": true}'))
    llm.probe(db, "openrouter/acme/small")
    [call] = db.scalars(select(AiCall)).all()
    assert (call.org_id, call.task, call.model, call.success) == (
        None,
        "settings_check",
        "openrouter/acme/small",
        True,
    )


@pytest.mark.parametrize("content", ['{"ok": false}', "Bonjour !", "[1, 2]"])
def test_a_model_that_does_not(db: Session, monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    monkeypatch.setattr(llm, "_call_provider", answering(content))
    with pytest.raises(llm.LlmError):
        llm.probe(db, "openrouter/acme/small")
    [call] = db.scalars(select(AiCall)).all()
    assert call.success is False and call.task == "settings_check"


def test_a_provider_error(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    def fails(*_: Any, **__: Any) -> Any:
        raise RuntimeError("No endpoints found matching your data policy")

    monkeypatch.setattr(llm, "_call_provider", fails)
    with pytest.raises(llm.LlmError) as exc:
        llm.probe(db, "openrouter/acme/small")
    assert "data policy" in str(exc.value)
    assert db.scalars(select(AiCall)).one().success is False


def test_the_trial_is_short(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider that hangs must not keep the operator waiting for minutes (final review)."""
    import litellm

    seen: dict[str, Any] = {}

    def completion(**kw: Any) -> Any:
        from types import SimpleNamespace

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
    llm.probe(db, "openrouter/acme/small")
    assert (seen["timeout"], seen["num_retries"]) == (60, 0)
