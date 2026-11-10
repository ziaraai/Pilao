"""Fixtures shared by the API tests."""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _fresh_admin_limiter() -> Iterator[None]:
    """The admin sign-in limiter is module-level: isolate each test."""
    from app.routers.admin import auth as admin_auth

    admin_auth._limiter._hits.clear()
    yield
    admin_auth._limiter._hits.clear()
