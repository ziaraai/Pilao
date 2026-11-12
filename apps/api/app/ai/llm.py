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

from app.ai.routing import provider_routing
from app.core.config import get_settings
from app.db.models import AiCall

# task name -> Settings attribute holding its model
TASK_MODELS = {
    "compliance_reading": "llm_model_vision",
    "dce_extraction": "llm_model_extraction",
    "memoir_generation": "llm_model_generation",
    "memoir_regeneration": "llm_model_generation",  # a new version of one chapter (lot 4)
    "profile_extraction": "llm_model_extraction",
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


class LlmTruncated(Exception):  # internal signal: never leaves this module
    """The answer hit the length limit: billed, but unusable as is."""

    def __init__(self, content: str, t_in: int, t_out: int, cost: float) -> None:
        super().__init__("answer truncated at the length limit")
        self.content, self.t_in, self.t_out, self.c = content, t_in, t_out, cost


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


def ensure_budget(db: Session, org_id: uuid.UUID) -> None:
    """Raise if the organization has used its monthly AI budget (all AI tasks included)."""
    if month_spend_eur(db, org_id) >= get_settings().ai_monthly_budget_eur_per_org:
        raise LlmBudgetExceeded("Budget IA mensuel de l'organisation atteint.")


DEFAULT_ANSWER_TOKENS = 4000  # retry budget of a truncated call that had no explicit limit


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


def _call_provider(
    model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
) -> tuple[str, int, int, float]:
    import litellm  # imported lazily: heavy, and unnecessary when no model is configured

    if max_tokens:  # the caller sizes the answer; recent models also reason before it
        max_tokens += get_settings().llm_reasoning_tokens
    resp = litellm.completion(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
        timeout=300 if max_tokens and max_tokens > 4000 else 90,
        num_retries=2,
        **({"max_tokens": max_tokens} if max_tokens else {}),
        **provider_routing(model),
    )
    content = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    # US dollars, converted: the journal and the budget are in euros
    cost = provider_cost_usd(litellm, resp) * get_settings().usd_eur_rate
    t_in = int(getattr(usage, "prompt_tokens", 0) or 0)
    t_out = int(getattr(usage, "completion_tokens", 0) or 0)
    if getattr(resp.choices[0], "finish_reason", None) == "length":
        raise LlmTruncated(content, t_in, t_out, cost)
    return content, t_in, t_out, cost


def provider_cost_usd(litellm: Any, resp: Any) -> float:
    """What the call was billed, in US dollars.

    The provider's own figure first (OpenRouter returns it with every answer): LiteLLM's
    price list does not know every model and then says 0, which would hide the cost from
    the journal and the monthly budget. The price list is only the fallback.
    """
    reported = (getattr(resp, "_hidden_params", None) or {}).get("response_cost")
    if not reported:
        reported = getattr(getattr(resp, "usage", None), "cost", None)
    if reported:
        return float(reported)
    try:
        return float(litellm.completion_cost(completion_response=resp) or 0.0)
    except Exception:  # noqa: BLE001 - unknown price for this model: log 0 rather than fail
        return 0.0


def complete[T: BaseModel](
    db: Session,
    *,
    org_id: uuid.UUID,
    task: str,
    messages: list[dict[str, Any]],
    response_model: type[T],
    prompt_version: str | None = None,
    bid_id: uuid.UUID | None = None,
    max_tokens: int | None = None,
) -> LlmResult[T]:
    model = model_for(task)
    ensure_budget(db, org_id)

    conversation = list(messages)
    in_tokens = out_tokens = 0
    cost = 0.0
    last_error = ""
    for attempt in range(2):  # one call + one corrective retry
        began = time.monotonic()
        try:
            content, t_in, t_out, c = _call_provider(model, conversation, max_tokens)
        except LlmTruncated as cut:  # asking to fix the JSON would be cut the same way
            in_tokens, out_tokens, cost = in_tokens + cut.t_in, out_tokens + cut.t_out, cost + cut.c
            last_error = "réponse tronquée : limite de longueur atteinte"
            _journal(
                db,
                org_id,
                bid_id,
                task,
                model,
                prompt_version,
                cut.t_in,
                cut.t_out,
                cut.c,
                began,
                last_error,
            )
            max_tokens = 2 * (max_tokens or DEFAULT_ANSWER_TOKENS)
            continue
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
