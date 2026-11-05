"""Where our requests may go: shared by every call to a model (text and embeddings)."""

from typing import Any

from app.core.config import get_settings


def provider_routing(model: str) -> dict[str, Any]:
    """Only providers that keep nothing of our clients' documents (privacy policy, docs/09).

    Through OpenRouter, ``data_collection: deny`` excludes every provider that stores the
    requests or may train on them; ``zdr`` keeps only zero-retention endpoints (stricter:
    some models have none). OpenRouter rejects an unknown value, so the option is enforced,
    not a wish.
    """
    if not model.startswith("openrouter/"):
        return {}
    s = get_settings()
    provider: dict[str, Any] = {}
    if s.llm_deny_data_collection:
        provider["data_collection"] = "deny"
    if s.llm_zero_data_retention:
        provider["zdr"] = True
    return {"extra_body": {"provider": provider}} if provider else {}
