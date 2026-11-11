"""A company suspended by the platform administration (lot 2, spec §2.2).

Suspending blocks the access, it erases nothing: no sign-in, no open session, no link sent by
e-mail works, the watch stops scoring notices and sending alerts. Reactivating gives it all back.
"""

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import Organization


def is_suspended(org: Organization) -> bool:
    return org.suspended_at is not None


def suspended_message() -> str:
    support = get_settings().support_email.strip()
    contact = f"Contactez Pilao : {support}." if support else "Contactez Pilao."
    return f"L'accès de votre entreprise à Pilao est suspendu. {contact}"


def suspended_error() -> ApiError:
    return ApiError(403, "account_suspended", suspended_message())


def contact_sentence() -> str:
    """The last line of an account e-mail sent on behalf of Pilao."""
    support = get_settings().support_email.strip()
    return (
        f"Pour toute question, contactez Pilao : {support}."
        if support
        else "Pour toute question, contactez Pilao."
    )
