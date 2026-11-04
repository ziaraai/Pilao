from collections.abc import Callable

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


def valid_siret(prefix: str) -> str:
    """Build a 14-digit SIRET with a valid Luhn check digit from a 13-digit prefix."""
    digits = prefix.ljust(13, "0")
    for check in range(10):
        candidate = f"{digits}{check}"
        total = 0
        for i, ch in enumerate(reversed(candidate)):
            d = int(ch)
            if i % 2 == 1:
                d = d * 2 - 9 if d * 2 > 9 else d * 2
            total += d
        if total % 10 == 0:
            return candidate
    raise AssertionError


def register_payload(n: int = 1) -> dict[str, str]:
    return {
        "email": f"user{n}@example.fr",
        "password": PASSWORD,
        "full_name": f"User {n}",
        "siret": valid_siret(f"1234567{n:06d}"),
        "org_name": f"Entreprise {n}",
    }


def signed_in_client(make_client: Callable[[], TestClient], outbox, n: int = 1) -> TestClient:  # type: ignore[no-untyped-def]
    client = make_client()
    assert client.post("/auth/register", json=register_payload(n)).status_code == 201
    assert client.post("/auth/verify-email", json={"token": outbox.last_token()}).status_code == 200
    res = client.post("/auth/login", json={"email": f"user{n}@example.fr", "password": PASSWORD})
    assert res.status_code == 200, res.text
    return client
