"""Colleagues of an organization (US-1.5): invitations, roles."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Role = Literal["org_admin", "org_member"]


class MemberOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    status: Literal["active", "invited", "invitation_expired"]
    invited_at: datetime | None
    last_login_at: datetime | None
    is_me: bool


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = "org_member"
    full_name: str | None = Field(default=None, max_length=200)


class RoleIn(BaseModel):
    role: Role


class InvitationLookupIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class InvitationOut(BaseModel):
    email: str
    full_name: str | None
    org_name: str
    role: str


class AcceptInvitationIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)
    accept_terms: bool = False
