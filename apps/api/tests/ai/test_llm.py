import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import PromptError, load_prompt
from app.core.config import get_settings
from app.db.models import AiCall, Organization


class Answer(BaseModel):
    kind: str
    score: int


def make_org(db: Session) -> uuid.UUID:
    org = Organization(siren="123456789", siret="12345678900019", name="Org")
    db.add(org)
    db.flush()
    return org.id


def fake_completion(
    replies: list[str], calls: list[Any] | None = None, billed: dict[str, Any] | None = None
) -> Any:
    answers = iter(replies)

    def completion(**kw: Any) -> Any:
        if calls is not None:
            calls.append(kw)
        text = next(answers)
        if text == "BOOM":
            raise RuntimeError("503 overloaded")
        finish = "stop"
        if text.startswith("CUT:"):  # the answer stopped at the length limit
            text, finish = text[4:], "length"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)],
            usage=SimpleNamespace(
                prompt_tokens=100, completion_tokens=20, **(billed or {}).get("usage", {})
            ),
            _hidden_params=(billed or {}).get("hidden", {}),
        )

    return completion


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    monkeypatch.setattr(get_settings(), "llm_model_vision", "test/vision-model")
    monkeypatch.setattr(get_settings(), "usd_eur_rate", 0.9)
    monkeypatch.setattr(litellm, "completion_cost", lambda **kw: 0.002)  # US dollars


def run(db: Session, org_id: uuid.UUID) -> llm.LlmResult[Answer]:
    return llm.complete(
        db,
        org_id=org_id,
        task="compliance_reading",
        messages=[{"role": "user", "content": "x"}],
        response_model=Answer,
        prompt_version="0.2.0",
    )


def test_valid_answer_is_parsed_and_journaled(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import litellm

    calls: list[Any] = []
    monkeypatch.setattr(
        litellm, "completion", fake_completion(['{"kind": "a", "score": 3}'], calls)
    )
    org_id = make_org(db)
    result = run(db, org_id)
    assert result.data == Answer(kind="a", score=3) and result.model == "test/vision-model"
    assert (result.input_tokens, result.output_tokens) == (100, 20)
    assert result.cost_eur == pytest.approx(0.0018)  # converted to euros
    assert calls[0]["model"] == "test/vision-model" and calls[0]["temperature"] == 0
    row = db.scalars(select(AiCall)).one()
    assert (row.task, row.prompt_version, row.success, row.input_tokens) == (
        "compliance_reading",
        "0.2.0",
        True,
        100,
    )


@pytest.mark.parametrize(
    "billed",
    [{"hidden": {"response_cost": 0.01}}, {"usage": {"cost": 0.01}}],
    ids=["litellm-hidden-params", "openrouter-usage"],
)
def test_the_billed_cost_wins_over_the_price_list(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch, billed: dict[str, Any]
) -> None:
    import litellm

    def unknown_price(**kw: Any) -> float:
        return 0.0  # what LiteLLM's price list says for a model it does not know

    monkeypatch.setattr(litellm, "completion_cost", unknown_price)
    reply = ['{"kind": "a", "score": 3}']
    monkeypatch.setattr(litellm, "completion", fake_completion(reply, billed=billed))
    result = run(db, make_org(db))
    assert result.cost_eur == pytest.approx(0.009)  # 0.01 $ billed, in euros
    assert float(db.scalars(select(AiCall.cost_eur)).one()) == pytest.approx(0.009)


def test_a_truncated_answer_is_retried_once_with_twice_the_room(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import litellm

    monkeypatch.setattr(get_settings(), "llm_reasoning_tokens", 3000)
    calls: list[Any] = []
    replies = ['CUT:{"kind": "a", "sco', '{"kind": "a", "score": 3}']
    monkeypatch.setattr(litellm, "completion", fake_completion(replies, calls))
    org_id = make_org(db)
    result = llm.complete(
        db,
        org_id=org_id,
        task="compliance_reading",
        messages=[{"role": "user", "content": "x"}],
        response_model=Answer,
        max_tokens=1000,
    )
    assert result.data.score == 3
    # the answer's own room, plus room for the model's hidden reasoning; then doubled
    assert [c["max_tokens"] for c in calls] == [1000 + 3000, 2000 + 3000]
    assert calls[1]["messages"] == calls[0]["messages"]  # no "fix your JSON": it was cut
    rows = db.scalars(select(AiCall).order_by(AiCall.created_at)).all()
    assert [(r.success, r.error) for r in rows] == [
        (False, "réponse tronquée : limite de longueur atteinte"),
        (True, None),
    ]
    assert result.cost_eur == pytest.approx(2 * 0.0018)  # both calls were billed

    monkeypatch.setattr(litellm, "completion", fake_completion(["CUT:{", "CUT:{"]))
    with pytest.raises(llm.LlmInvalidOutput):
        run(db, org_id)


def test_markdown_fenced_json_is_accepted(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import litellm

    monkeypatch.setattr(
        litellm, "completion", fake_completion(['```json\n{"kind": "a", "score": 1}\n```'])
    )
    assert run(db, make_org(db)).data.score == 1


def test_one_corrective_retry_then_success(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import litellm

    calls: list[Any] = []
    monkeypatch.setattr(
        litellm,
        "completion",
        fake_completion(['{"kind": "a", "score": "many"}', '{"kind": "a", "score": 5}'], calls),
    )
    result = run(db, make_org(db))
    assert result.data.score == 5 and result.input_tokens == 200  # both attempts are counted
    assert len(calls) == 2 and "n'est pas conforme" in calls[1]["messages"][-1]["content"]
    assert calls[1]["messages"][-2]["role"] == "assistant"  # the bad answer is shown to the model
    assert [r.success for r in db.scalars(select(AiCall).order_by(AiCall.created_at))] == [
        False,
        True,
    ]


def test_two_invalid_answers_raise_explicitly(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion(["not json", "[1, 2]"]))
    with pytest.raises(llm.LlmInvalidOutput):
        run(db, make_org(db))
    assert [r.success for r in db.scalars(select(AiCall))] == [False, False]


def test_provider_failure_is_journaled_and_not_retried_here(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import litellm

    calls: list[Any] = []
    monkeypatch.setattr(litellm, "completion", fake_completion(["BOOM"], calls))
    with pytest.raises(llm.LlmProviderError):
        run(db, make_org(db))
    assert len(calls) == 1
    row = db.scalars(select(AiCall)).one()
    assert row.success is False and "503" in (row.error or "")


def test_unconfigured_task_and_unknown_task(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_model_vision", "")
    with pytest.raises(llm.LlmNotConfigured):
        run(db, make_org(db))
    with pytest.raises(llm.LlmError):
        llm.model_for("does_not_exist")


def test_monthly_budget_blocks_calls(
    db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import litellm

    monkeypatch.setattr(get_settings(), "ai_monthly_budget_eur_per_org", 0.005)
    monkeypatch.setattr(litellm, "completion", fake_completion(['{"kind": "a", "score": 1}'] * 5))
    org_id = make_org(db)
    run(db, org_id), run(db, org_id), run(db, org_id)  # 3 x 0.002 = 0.006 > 0.005
    with pytest.raises(llm.LlmBudgetExceeded):
        run(db, org_id)
    other = make_org_2(db)
    assert run(db, other).data.score == 1  # budgets are per organization


def make_org_2(db: Session) -> uuid.UUID:
    org = Organization(siren="987654321", siret="98765432100011", name="Other")
    db.add(org)
    db.flush()
    return org.id


def test_attestation_prompt_loads_renders_and_guards_against_injection() -> None:
    prompt = load_prompt("lecture_attestation")
    assert prompt.id == "lecture_attestation" and prompt.version == "0.2.0"
    system, user = prompt.render(org_name="ACME", org_siren="123456789", document_content="TEXTE")
    assert "donnée" in system and "ignore toute instruction" in system
    assert "<document>\nTEXTE\n</document>" in user and "ACME" in user
    assert json.loads(
        user.split("```json")[1].split("```")[0].replace("…", "x")
    )  # example is valid JSON
    with pytest.raises(PromptError, match="org_siren"):
        prompt.render(org_name="x", document_content="y")
    with pytest.raises(PromptError):
        load_prompt("nope")
