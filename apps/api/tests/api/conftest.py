"""Fixtures shared by the API tests."""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _fresh_admin_limiter() -> Iterator[None]:
    """The sign-in limiters are module-level: isolate each test."""
    from app.routers import auth as client_auth
    from app.routers.admin import auth as admin_auth

    for limiter in (admin_auth._limiter, client_auth._password_limiter):
        limiter._hits.clear()
    yield
    for limiter in (admin_auth._limiter, client_auth._password_limiter):
        limiter._hits.clear()
