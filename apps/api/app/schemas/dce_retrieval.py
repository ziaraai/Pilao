import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, StringConstraints

Mode = Literal["identified", "anonymous"]


def _blank_is_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


Name = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None,
    BeforeValidator(_blank_is_none),
]
Email = Annotated[EmailStr | None, BeforeValidator(_blank_is_none)]


class ContactIO(BaseModel):
    """The contact given to the buyers' platforms when the DCE is retrieved on the company's
    behalf (spec « Récupération des DCE », § 4.2)."""

    first_name: Name = None
    last_name: Name = None
    email: Email = None


class RetrievalSettingsIO(BaseModel):
    mode: Mode | None = None
    contact: ContactIO = ContactIO()


class SourceIn(BaseModel):
    url: Annotated[str, StringConstraints(max_length=2000)] | None = None


class RetrieveIn(BaseModel):
    mode: Mode | None = None
    remember: bool = False
    contact: ContactIO | None = None


class DceFetchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    mode: str | None
    status: str
    outcome: str | None
    message: str | None
    site: str
    created_at: datetime
    finished_at: datetime | None


class DceWatchOut(BaseModel):
    checked_at: datetime | None = None
    size_label: str | None = None
    deadline_at: datetime | None = None
    failures: int = 0
    stopped: bool = False


class DceSourceOut(BaseModel):
    url: str | None
    platform: str | None
    site: str | None
    automatic: bool
    home_only: bool
    guide: list[str]
    terms_url: str | None
    robot_enabled: bool
    mode: Mode | None
    contact: ContactIO
    last_fetch: DceFetchOut | None
    watch: DceWatchOut | None
