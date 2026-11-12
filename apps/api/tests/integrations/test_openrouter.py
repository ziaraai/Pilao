"""Lot 5: OpenRouter's catalogue, key check and credit (answers shaped like the real ones,
read on 2026-11-12)."""

from typing import Any

import httpx
import pytest

from app.ai.openrouter import CatalogueModel, KeyRefused, OpenRouter, OpenRouterUnavailable

HAIKU = {
    "id": "anthropic/claude-haiku-5.5",
    "name": "Anthropic: Claude Haiku 5.5",
    "pricing": {"prompt": "0.0000001", "completion": "0.0000005", "web_search": "0.01"},
    "context_length": 1000000,
    "architecture": {"input_modalities": ["text", "image", "file"], "output_modalities": ["text"]},
    "supported_parameters": ["max_tokens", "response_format", "structured_outputs"],
}
FREE = {**HAIKU, "id": "baidu/ernie-5.5-flash-preview:free", "name": "Ernie (free)"}
AUTO = {**HAIKU, "id": "openrouter/auto", "name": "Auto", "pricing": {"prompt": "-1"}}
BARE = {"id": "acme/bare", "name": "Bare", "pricing": {"prompt": "0", "completion": "0"}}
BROKEN = {"name": "no id"}


def client(handler: Any) -> OpenRouter:
    return OpenRouter(
        "https://or.test/api/v1", httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_the_catalogue_is_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/models"
        return httpx.Response(200, json={"data": [HAIKU, FREE, AUTO, BARE, BROKEN]})

    models = {m.id: m for m in client(handler).models()}
    assert set(models) == {HAIKU["id"], FREE["id"], AUTO["id"], BARE["id"]}  # BROKEN skipped
    haiku = models[HAIKU["id"]]
    assert haiku == CatalogueModel(
        id="anthropic/claude-haiku-5.5",
        name="Anthropic: Claude Haiku 5.5",
        prompt_usd=0.0000001,
        completion_usd=0.0000005,
        context_length=1000000,
        json_output=True,
        reads_images=True,
    )
    assert models[AUTO["id"]].prompt_usd == -1.0  # kept here, refused by ai_catalogue.usable
    bare = models[BARE["id"]]
    assert (bare.json_output, bare.reads_images, bare.context_length) == (False, False, 0)


def test_the_key_is_checked() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/key"
        seen.append(request.headers["authorization"])
        good = request.headers["authorization"] == "Bearer sk-or-v1-good"
        return httpx.Response(200 if good else 401, json={"data": {"usage": 0.29}})

    or_ = client(handler)
    or_.check_key("sk-or-v1-good")
    with pytest.raises(KeyRefused) as refused:
        or_.check_key("sk-or-v1-bad")
    assert "sk-or-v1-bad" not in str(refused.value)  # never the key in a message
    assert seen == ["Bearer sk-or-v1-good", "Bearer sk-or-v1-bad"]


def test_the_credit_is_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/credits"
        return httpx.Response(200, json={"data": {"total_credits": 5, "total_usage": 1.32471089}})

    credit = client(handler).credit("sk-or-v1-good")
    assert (credit.total_usd, credit.used_usd) == (5.0, 1.32471089)


def test_openrouter_unreachable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    for handler in (down, broken):
        or_ = client(handler)
        with pytest.raises(OpenRouterUnavailable):
            or_.models()
        with pytest.raises(OpenRouterUnavailable) as exc:
            or_.check_key("sk-or-v1-secret")
        assert "sk-or-v1-secret" not in str(exc.value)
        with pytest.raises(OpenRouterUnavailable):
            or_.credit("sk-or-v1-secret")
