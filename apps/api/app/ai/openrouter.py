"""OpenRouter's own API, outside LiteLLM (lot 5): its model catalogue, the check of a key and
the credit of the account (docs/07, read on 2026-11-12).

``GET /models`` is public; ``GET /key`` and ``GET /credits`` take the key as a bearer token.
A key never appears in an exception message or a log line.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings


class OpenRouterUnavailable(Exception):
    """OpenRouter did not answer, or not as expected (network, 5xx, unreadable JSON)."""


class KeyRefused(Exception):
    """OpenRouter refuses the key (401 or 403)."""


@dataclass(frozen=True)
class CatalogueModel:
    id: str
    name: str
    prompt_usd: float  # dollars per token
    completion_usd: float
    context_length: int
    json_output: bool
    reads_images: bool


@dataclass(frozen=True)
class Credit:
    total_usd: float
    used_usd: float


def _price(pricing: dict[str, Any], key: str) -> float:
    try:
        return float(pricing.get(key))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1.0  # unknown: refused by ai_catalogue.usable


def _model(item: dict[str, Any]) -> CatalogueModel | None:
    model_id = item.get("id")
    if not isinstance(model_id, str) or not model_id:
        return None
    pricing = item.get("pricing") or {}
    arch = item.get("architecture") or {}
    params = item.get("supported_parameters") or []
    if not isinstance(params, list):
        raise TypeError("supported_parameters")
    try:
        context = int(item.get("context_length") or 0)
    except (TypeError, ValueError):
        context = 0
    return CatalogueModel(
        id=model_id,
        name=str(item.get("name") or model_id),
        prompt_usd=_price(pricing, "prompt"),
        completion_usd=_price(pricing, "completion"),
        context_length=context,
        json_output="response_format" in params,
        reads_images="image" in (arch.get("input_modalities") or []),
    )


class OpenRouter:
    def __init__(
        self, base_url: str, http: httpx.Client | None = None, timeout: float = 10
    ) -> None:
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=timeout)

    def _get(
        self, path: str, key: str | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        extra: dict[str, Any] = {"timeout": timeout} if timeout else {}
        try:
            resp = self._http.get(f"{self._base}{path}", headers=headers, **extra)
        except httpx.HTTPError as exc:
            raise OpenRouterUnavailable(f"OpenRouter injoignable ({type(exc).__name__})") from None
        if key and resp.status_code in (401, 403):  # without a key (the catalogue): unavailable
            raise KeyRefused("Clé refusée par OpenRouter.")
        if resp.status_code != 200:
            raise OpenRouterUnavailable(f"OpenRouter a répondu {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise OpenRouterUnavailable("réponse illisible d'OpenRouter") from None
        if not isinstance(body, dict):
            raise OpenRouterUnavailable("réponse inattendue d'OpenRouter")
        return body

    def models(self, timeout: float | None = None) -> list[CatalogueModel]:
        items = self._get("/models", timeout=timeout).get("data") or []
        if not isinstance(items, list):
            raise OpenRouterUnavailable("catalogue illisible")
        found = []
        for item in items:
            try:
                model = _model(item) if isinstance(item, dict) else None
            except (AttributeError, TypeError, ValueError):
                model = None  # an unreadable entry is skipped, never an error
            if model is not None:
                found.append(model)
        return found

    def check_key(self, key: str) -> None:
        self._get("/key", key)

    def credit(self, key: str) -> Credit:
        data = self._get("/credits", key).get("data") or {}
        try:
            return Credit(float(data["total_credits"]), float(data["total_usage"]))
        except (KeyError, TypeError, ValueError):
            raise OpenRouterUnavailable("crédit illisible") from None


def get_openrouter() -> OpenRouter:
    """FastAPI dependency (tests replace it)."""
    return OpenRouter(get_settings().openrouter_api_url)
