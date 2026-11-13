import socket
from typing import Any

import pytest

from app.integrations.robot_net import is_public_address, url_allowed


@pytest.mark.parametrize(
    "ip", ["10.0.0.1", "127.0.0.1", "169.254.169.254", "::1", "192.168.1.1", "0.0.0.0", "fc00::1"]
)
def test_private_addresses(ip: str) -> None:
    assert not is_public_address(ip)


def test_public_address() -> None:
    assert is_public_address("185.24.184.10")


def _resolves_to(monkeypatch: pytest.MonkeyPatch, ip: str) -> list[str]:
    asked: list[str] = []

    def fake(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        asked.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    return asked


def test_https_to_a_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolves_to(monkeypatch, "185.24.184.10")
    assert url_allowed("https://www.marches-publics.gouv.fr/entreprise/consultation/1", False)


def test_http_refused_without_the_test_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolves_to(monkeypatch, "185.24.184.10")
    assert not url_allowed("http://www.marches-publics.gouv.fr/", False)
    assert url_allowed("http://www.marches-publics.gouv.fr/", True)


def test_a_name_that_points_inside(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolves_to(monkeypatch, "10.0.0.7")
    assert not url_allowed("https://intranet.exemple.fr/", False)


def test_localhost_and_literal_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _resolves_to(monkeypatch, "185.24.184.10")
    assert not url_allowed("https://localhost/", False)
    assert url_allowed("https://localhost/", True)
    assert not url_allowed("https://10.0.0.5/entreprise/consultation/1", False)
    assert not url_allowed("https://[::1]/", False)
    assert asked == []  # no lookup for these


def test_without_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _resolves_to(monkeypatch, "10.0.0.7")
    assert url_allowed("https://intranet.exemple.fr/", False, resolve=False)  # checked later
    assert not url_allowed("https://127.0.0.1/", False, resolve=False)
    assert not url_allowed("ftp://exemple.fr/", False, resolve=False)
    assert asked == []


def test_unresolvable_name_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> list[Any]:
        raise socket.gaierror("no such name")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    assert not url_allowed("https://nulle-part.exemple/", False)
