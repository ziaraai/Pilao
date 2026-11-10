"""Encryption of the secrets Pilao must be able to read back (authenticator secrets, API keys).

One key per ``purpose``, derived from ``APP_SECRET_KEY``: a value encrypted for one purpose
cannot be decrypted for another. Changing ``APP_SECRET_KEY`` makes every stored value
unreadable (:class:`DecryptError`): the owner then sets it again.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings


class DecryptError(Exception):
    """The value is not ours, was altered, or was encrypted with another key or purpose."""


def _fernet(purpose: str) -> Fernet:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose.encode()).derive(
        get_settings().app_secret_key.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str, purpose: str) -> str:
    return _fernet(purpose).encrypt(plaintext.encode()).decode()


def decrypt(token: str, purpose: str) -> str:
    try:
        return _fernet(purpose).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise DecryptError("unreadable value") from exc
