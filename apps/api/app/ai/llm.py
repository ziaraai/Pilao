"""The single entry point for language-model calls (CLAUDE.md §3).

* the model is chosen per *task* from configuration (``LLM_MODEL_*``);
* structured output is validated by a Pydantic model: on failure, ONE corrective retry,
  then an explicit error (never a half-parsed result);
* every attempt is journaled in ``ai_calls`` (task, model, tokens, cost, latency);
* a monthly budget per organization stops runaway costs.

Note: this module commits the session after journaling, so that failed attempts survive a
later rollback. Call it when the session holds no uncommitted work you want to keep atomic.
"""

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AiCall

# task name -> Settings attribute holding its model
TASK_MODELS = {
    "compliance_reading": "llm_model_vision",
    "dce_extraction": "llm_model_extraction",
    "memoir_generation": "llm_model_generation",
    "tender_scoring": "llm_model_scoring",
}


class LlmError(Exception):
    """Base class: the message is safe to show to the user."""


class LlmNotConfigured(LlmError):
    pass


class LlmBudgetExceeded(LlmError):
    pass


class LlmProviderError(LlmError):
    pass


class LlmInvalidOutput(LlmError):
    pass


@dataclass(frozen=True)
class LlmResult[T: BaseModel]:
    data: T
    raw: dict[str, Any]
    model: str
    prompt_version: str | None
    input_tokens: int
    output_tokens: int
    cost_eur: float


def model_for(task: str) -> str:
    attr = TASK_MODELS.get(task)
    if attr is None:
        raise LlmError(f"unknown AI task: {task}")
    model: str = getattr(get_settings(), attr)
    if not model:
        raise LlmNotConfigured(f"Aucun modèle configuré pour la tâche « {task} ».")
    return model


def month_spend_eur(db: Session, org_id: uuid.UUID) -> float:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(
        select(func.coalesce(func.sum(AiCall.cost_eur), 0)).where(
            AiCall.org_id == org_id, AiCall.created_at >= start
        )
    )
    return float(total or 0)


def parse_json_object(text: str) -> dict[str, Any]:
    """Accept raw JSON or JSON wrapped in a Markdown code fence."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n(.*?)\n```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError("the answer must be a JSON object")
    return data


def _call_provider(model: str, messages: list[dict[str, Any]]) -> tuple[str, int, int, float]:
    import litellm  # imported lazily: heavy, and unnecessary when no model is configured

    resp = litellm.completion(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
        timeout=90,
        num_retries=2,
    )
    content = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    try:
        cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
    except Exception:  # noqa: BLE001 - unknown price for this model: log 0 rather than fail
        cost = 0.0
    return (
        content,
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
        cost,
    )


def complete[T: BaseModel](
    db: Session,
    *,
    org_id: uuid.UUID,
    task: str,
    messages: list[dict[str, Any]],
    response_model: type[T],
    prompt_version: str | None = None,
    bid_id: uuid.UUID | None = None,
) -> LlmResult[T]:
    model = model_for(task)
    budget = get_settings().ai_monthly_budget_eur_per_org
    if month_spend_eur(db, org_id) >= budget:
        raise LlmBudgetExceeded("Budget IA mensuel de l'organisation atteint.")

    conversation = list(messages)
    in_tokens = out_tokens = 0
    cost = 0.0
    last_error = ""
    for attempt in range(2):  # one call + one corrective retry
        began = time.monotonic()
        try:
            content, t_in, t_out, c = _call_provider(model, conversation)
        except Exception as exc:
            _journal(
                db, org_id, bid_id, task, model, prompt_version, 0, 0, 0.0, began, str(exc)[:500]
            )
            raise LlmProviderError("Le service d'IA est momentanément indisponible.") from exc
        in_tokens, out_tokens, cost = in_tokens + t_in, out_tokens + t_out, cost + c
        try:
            raw = parse_json_object(content)
            data = response_model.model_validate(raw)
        except (ValueError, TypeError, ValidationError) as exc:
            last_error = str(exc)[:500]
            _journal(
                db, org_id, bid_id, task, model, prompt_version, t_in, t_out, c, began, last_error
            )
            conversation = [
                *conversation,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": "Ta réponse n'est pas conforme au format demandé "
                    f"({last_error}). Réponds uniquement avec le JSON corrigé.",
                },
            ]
            continue
        _journal(db, org_id, bid_id, task, model, prompt_version, t_in, t_out, c, began, None)
        return LlmResult(data, raw, model, prompt_version, in_tokens, out_tokens, cost)
    raise LlmInvalidOutput("Le modèle n'a pas produit de réponse exploitable.")


def _journal(
    db: Session,
    org_id: uuid.UUID,
    bid_id: uuid.UUID | None,
    task: str,
    model: str,
    prompt_version: str | None,
    t_in: int,
    t_out: int,
    cost: float,
    began: float,
    error: str | None,
) -> None:
    db.add(
        AiCall(
            org_id=org_id,
            bid_id=bid_id,
            task=task,
            model=model,
            prompt_version=prompt_version,
            input_tokens=t_in,
            output_tokens=t_out,
            cost_eur=Decimal(str(round(cost, 5))),
            latency_ms=int((time.monotonic() - began) * 1000),
            success=error is None,
            error=error,
        )
    )
    db.commit()
