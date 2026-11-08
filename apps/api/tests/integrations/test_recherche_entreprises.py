import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.integrations.recherche_entreprises import (
    CompanyLookupUnavailable,
    RechercheEntreprisesClient,
    parse_company,
)

SAMPLE: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "recherche_entreprises_sample.json").read_text()
)
SIRET = "12345678900019"


def make_client(handler: Any, sleeps: list[float] | None = None) -> RechercheEntreprisesClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return RechercheEntreprisesClient(
        "https://api.test", http, sleep=(sleeps if sleeps is not None else []).append
    )


def test_parse_headquarters() -> None:
    info = parse_company(SAMPLE, SIRET)
    assert info is not None
    assert (info.siren, info.name, info.legal_form, info.naf_code) == (
        "123456789",
        "NETTOYAGE EXEMPLE",  # the legal name, without « (N.E.) »
        "5710",
        "81.21Z",
    )
    # the street alone: « adresse » repeats the postal code and the town
    assert info.address_line == "1 B RUE DE LA PAIX, BATIMENT A"
    assert (info.postal_code, info.city, info.department) == ("75002", "PARIS", "75")
    assert info.is_active is True and info.headcount_range == "12"
    # listed twice by the registry, once here; legal entities are not people
    assert info.managers == ("JEANNE DUPONT",)
    twice = {
        "results": [
            {
                "nom_complet": "X",
                "siege": {"siret": SIRET},
                "dirigeants": [
                    {"nom": "MARTIN", "prenoms": "JEAN PIERRE"},
                    {"nom": "MARTIN (MARTIN)", "prenoms": "JEAN-PIERRE"},
                ],
            }
        ]
    }
    again = parse_company(twice, SIRET)
    assert again is not None and again.managers == ("JEAN PIERRE MARTIN",)


def test_parse_secondary_establishment() -> None:
    info = parse_company(SAMPLE, "12345678900027")
    assert info is not None and info.city == "LYON" and info.name == "NETTOYAGE EXEMPLE"
    assert info.address_line == "5 AVENUE X"
    assert info.department == "69"  # not given for an establishment: from the postal code


def test_street_falls_back_to_the_full_address() -> None:
    payload = {
        "results": [
            {
                "nom_complet": "X",
                "siege": {
                    "siret": SIRET,
                    "adresse": "20 BOULEVARD MARTIN BERNARD 42000 SAINT-ETIENNE",
                    "code_postal": "42000",
                },
            }
        ]
    }
    info = parse_company(payload, SIRET)
    assert info is not None and info.address_line == "20 BOULEVARD MARTIN BERNARD"
    assert info.name == "X" and info.department == "42"


def test_parse_unknown_siret_and_empty_payload() -> None:
    assert parse_company(SAMPLE, "99999999999999") is None
    assert parse_company({}, SIRET) is None
    assert parse_company({"results": [{"siege": {}}]}, SIRET) is None


def test_lookup_sends_siret_and_caches() -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json=SAMPLE)

    client = make_client(handler)
    assert client.lookup_siret(SIRET) is not None
    assert client.lookup_siret(SIRET) is not None
    assert len(calls) == 1 and calls[0].url.params["q"] == SIRET


def test_not_found_is_cached_as_none() -> None:
    client = make_client(lambda r: httpx.Response(200, json={"results": []}))
    assert client.lookup_siret(SIRET) is None


def test_retries_on_429_then_succeeds() -> None:
    answers = iter([429, 503, 200])
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        code = next(answers)
        return httpx.Response(
            code,
            json=SAMPLE if code == 200 else {},
            headers={"retry-after": "1"} if code == 429 else {},
        )

    client = make_client(handler, sleeps)
    assert client.lookup_siret(SIRET) is not None
    assert len(sleeps) == 2 and sleeps[0] == 1.0


def test_gives_up_after_three_attempts() -> None:
    n = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return httpx.Response(500)

    with pytest.raises(CompanyLookupUnavailable):
        make_client(handler).lookup_siret(SIRET)
    assert n == 3


def test_network_error_and_bad_json_are_unavailable() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(CompanyLookupUnavailable):
        make_client(boom).lookup_siret(SIRET)
    with pytest.raises(CompanyLookupUnavailable):
        make_client(lambda r: httpx.Response(200, content=b"<html>")).lookup_siret(SIRET)


def test_client_error_is_not_retried() -> None:
    n = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return httpx.Response(400)

    with pytest.raises(CompanyLookupUnavailable):
        make_client(handler).lookup_siret(SIRET)
    assert n == 1


def test_rejects_malformed_siret() -> None:
    with pytest.raises(ValueError):
        make_client(lambda r: httpx.Response(200, json={})).lookup_siret("123")


@pytest.mark.parametrize(
    "payload",
    [{"results": ["oops"]}, {"results": {"siren": "1"}}, {"results": [{"siege": "x"}]}],
)
def test_unexpected_shape_is_not_a_crash(payload: dict[str, Any]) -> None:
    client = make_client(lambda r: httpx.Response(200, json=payload))
    assert client.lookup_siret(SIRET) is None


def test_unparseable_payload_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations import recherche_entreprises as mod

    def broken(payload: dict[str, Any], siret: str) -> None:
        raise TypeError("shape changed")

    monkeypatch.setattr(mod, "parse_company", broken)
    with pytest.raises(CompanyLookupUnavailable):
        make_client(lambda r: httpx.Response(200, json=SAMPLE)).lookup_siret(SIRET)


def test_decoding_error_is_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError("bad gzip")

    with pytest.raises(CompanyLookupUnavailable):
        make_client(handler).lookup_siret(SIRET)


def test_retry_after_http_date_falls_back_to_backoff() -> None:
    answers = iter([429, 200])
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        code = next(answers)
        headers = {"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"} if code == 429 else {}
        return httpx.Response(code, json=SAMPLE if code == 200 else {}, headers=headers)

    assert make_client(handler, sleeps).lookup_siret(SIRET) is not None
    assert sleeps == [0.5]


def test_cache_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations import recherche_entreprises as mod

    monkeypatch.setattr(mod, "CACHE_MAX_ENTRIES", 3)
    client = make_client(lambda r: httpx.Response(200, json={"results": []}))
    for i in range(10):
        client.lookup_siret(f"{i:014d}")
    assert len(client._cache) <= 3
