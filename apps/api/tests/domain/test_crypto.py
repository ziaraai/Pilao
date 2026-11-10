"""Secrets kept in the database are encrypted with a key derived from APP_SECRET_KEY."""

import pytest

from app.core import crypto
from app.core.config import get_settings


def test_round_trip() -> None:
    token = crypto.encrypt("JBSWY3DP", "p")
    assert "JBSWY3DP" not in token
    assert crypto.decrypt(token, "p") == "JBSWY3DP"


def test_wrong_purpose_tampered_or_other_key(monkeypatch: pytest.MonkeyPatch) -> None:
    token = crypto.encrypt("x", "p")
    for bad_token, purpose in ((token, "q"), (token[:-2] + "AA", "p"), ("pas-un-jeton", "p")):
        with pytest.raises(crypto.DecryptError):
            crypto.decrypt(bad_token, purpose)
    monkeypatch.setattr(get_settings(), "app_secret_key", "une-autre-cle-de-plus-de-32-caracteres")
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(token, "p")
