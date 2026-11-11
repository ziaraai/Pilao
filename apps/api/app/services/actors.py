"""Who does something in a company's space: one of its users, or Pilao (the administration).

The company rules (``members``, ``org_data``) take an :data:`Actor` so that the administration
runs exactly the same rules, on behalf of Pilao (lot 2, ADR-042). An action by Pilao is written
in the company's history without a user (``user_id`` empty) and with ``meta.by = "pilao"``.
"""

import uuid
from dataclasses import dataclass

from app.db.models import User

PILAO_NAME = "L'équipe Pilao"


@dataclass(frozen=True)
class PlatformActor:
    """A super admin acting from the administration."""

    admin_id: uuid.UUID
    email: str


type Actor = User | PlatformActor


def user_id_of(actor: Actor) -> uuid.UUID | None:
    return actor.id if isinstance(actor, User) else None


def meta_of(actor: Actor) -> dict[str, str]:
    return {} if isinstance(actor, User) else {"by": "pilao"}


def name_of(actor: Actor) -> str:
    return (actor.full_name or actor.email) if isinstance(actor, User) else PILAO_NAME
