import re
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def siret_ok(siret: str) -> bool:
    """14 digits with a valid Luhn key. La Poste (SIREN 356000000) has legitimate SIRETs that
    fail Luhn; accept them."""
    return bool(re.fullmatch(r"\d{14}", siret)) and (
        luhn_ok(siret) or siret.startswith("356000000")
    )


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    full_name: str = Field(min_length=1, max_length=200)
    siret: str
    org_name: str = Field(min_length=1, max_length=300)
    accept_terms: bool = False  # CGU, privacy policy and processing agreement

    @field_validator("siret")
    @classmethod
    def _siret(cls, v: str) -> str:
        v = re.sub(r"\s+", "", v)
        if not siret_ok(v):
            raise ValueError("SIRET invalide")
        return v


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ResendIn(BaseModel):
    email: EmailStr


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    siret: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    org: OrgOut


class MessageOut(BaseModel):
    message: str
