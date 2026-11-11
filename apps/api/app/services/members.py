"""Colleagues of an organization (US-1.5).

An administrator invites a colleague by e-mail: the account is created without a password,
and a single-use link (``auth_tokens``, kind ``invitation``, 7 days) lets the colleague
choose a password and accept the terms; the link proves the address, and opens a session.

Rules:

* only administrators manage colleagues; every colleague sees the list;
* an organization always keeps an administrator: the last one can neither be demoted nor
  removed, and nobody removes themselves (another administrator does it, or the whole
  company is deleted, ADR-026);
* removing a colleague deletes the account and its sessions; their work stays (authors
  become empty: every reference to ``users`` is ``SET NULL``).
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Email, Mailer, send_quietly
from app.core.errors import ApiError
from app.core.legal import TERMS_VERSION
from app.core.security import hash_password, hash_token, new_token
from app.db.models import AuditLog, AuthToken, Organization, User, UserSession
from app.schemas.members import AcceptInvitationIn, InvitationOut, InviteIn, MemberOut
from app.services.actors import PILAO_NAME, Actor, PlatformActor, meta_of, name_of, user_id_of
from app.services.auth import LINK_CAP_MESSAGE, open_session, too_many_links
from app.services.suspension import is_suspended, suspended_error

INVITE_KIND = "invitation"
INVALID_LINK = (
    "Ce lien d'invitation n'est plus valable : demandez-en un nouveau à votre administrateur."
)


def _now() -> datetime:
    return datetime.now(UTC)


def _audit(db: Session, actor: Actor, action: str, target: uuid.UUID) -> None:
    db.add(
        AuditLog(
            user_id=user_id_of(actor),
            action=action,
            entity="user",
            entity_id=target,
            meta=meta_of(actor),
        )
    )


# ---------- the list ------------------------------------------------------------------


def list_members(db: Session, me: User) -> list[MemberOut]:
    """Scoped session: this organization's accounts only."""
    users = db.scalars(select(User).order_by(User.created_at)).all()
    links = {
        t.user_id: t
        for t in db.scalars(
            select(AuthToken).where(AuthToken.kind == INVITE_KIND).order_by(AuthToken.created_at)
        )
    }  # the latest invitation of each colleague
    now = _now()
    out = []
    for u in users:
        link = links.get(u.id)
        if u.password_hash is not None:
            status = "active"
        elif link is not None and link.used_at is None and link.expires_at > now:
            status = "invited"
        else:
            status = "invitation_expired"
        out.append(
            MemberOut(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                status=status,
                invited_at=u.created_at if u.password_hash is None else None,
                last_login_at=u.last_login_at,
                is_me=u.id == me.id,
            )
        )
    return out


# ---------- inviting ------------------------------------------------------------------


def _invitation(
    db: Session, user: User, org: Organization, inviter: Actor, first_access: bool = False
) -> Email:
    """Stage a new link; send the returned e-mail once it is committed.

    ``first_access``: Pilao opened the company's space and this is its first person."""
    s = get_settings()
    token = new_token()
    db.add(
        AuthToken(
            org_id=org.id,
            user_id=user.id,
            kind=INVITE_KIND,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(hours=s.invitation_ttl_hours),
        )
    )
    who = name_of(inviter)
    days = s.invitation_ttl_hours // 24
    link = f"{s.app_base_url}/invitation?token={token}"
    if isinstance(inviter, PlatformActor) and first_access:
        hello = f"Bonjour {user.full_name}," if user.full_name else "Bonjour,"
        return Email(
            to=user.email,
            subject=f"Pilao a ouvert l'espace de {org.name}",
            body=(
                f"{hello}\n\n{PILAO_NAME} a ouvert l'espace de {org.name} sur Pilao, la "
                "plateforme qui vous aide à répondre aux appels d'offres publics.\n\n"
                f"Choisissez votre mot de passe pour y entrer (lien valable {days} jours) :\n"
                f"{link}\n"
            ),
        )
    return Email(
        to=user.email,
        subject=f"{who} vous invite sur Pilao ({org.name})",
        body=(
            f"Bonjour,\n\n{who} vous invite à rejoindre l'espace de {org.name} sur Pilao, "
            "pour préparer ensemble les réponses aux appels d'offres.\n\n"
            f"Pour créer votre accès, ouvrez ce lien (valable {days} jours) :\n"
            f"{link}\n\n"
            f"Si vous ne connaissez pas {org.name}, ignorez ce message.\n"
        ),
    )


def invite(
    db: Session,
    actor: Actor,
    org: Organization,
    data: InviteIn,
    mailer: Mailer,
    *,
    first_access: bool = False,
) -> User:
    email = str(data.email).lower()
    # An address belongs to one account in all Pilao: the unique index (case-insensitive)
    # says so below, without this scoped session ever reading another company's accounts.
    count = db.scalar(select(func.count()).select_from(User)) or 0
    if count >= get_settings().max_users_per_org:
        raise ApiError(409, "too_many_users", "Nombre maximal d'utilisateurs atteint.")
    user = User(
        org_id=org.id,
        email=email,
        full_name=(data.full_name or "").strip() or None,
        role=data.role,
        password_hash=None,
    )
    try:
        db.add(user)
        db.flush()
        _audit(db, actor, "invite", user.id)
        message = _invitation(db, user, org, actor, first_access)
        db.commit()
    except IntegrityError:  # the same address invited or registered at the same moment
        db.rollback()
        raise ApiError(409, "email_taken", "Cette adresse e-mail a déjà un compte Pilao.") from None
    mailer.send(message)
    return user


def colleague(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)  # scoped: another organization's account is not found
    if user is None:
        raise ApiError(404, "not_found", "Utilisateur introuvable.")
    return user


def resend(
    db: Session, actor: Actor, org: Organization, user_id: uuid.UUID, mailer: Mailer
) -> None:
    user = colleague(db, user_id)
    if user.password_hash is not None:
        raise ApiError(409, "already_active", "Ce collaborateur a déjà créé son accès.")
    if too_many_links(db, user.id, INVITE_KIND):
        raise ApiError(429, "too_many_invitations", LINK_CAP_MESSAGE)
    message = _invitation(db, user, org, actor)
    _audit(db, actor, "resend_invitation", user.id)
    db.commit()
    mailer.send(message)


def reinvite(db: Session, user: User, org: Organization, mailer: Mailer) -> bool:
    """« Mot de passe oublié » for an account never created: a fresh invitation link instead.

    Capped like ``resend``; ``False`` when the cap is reached (nothing leaves)."""
    s = get_settings()
    if too_many_links(db, user.id, INVITE_KIND):
        return False
    token = new_token()
    db.add(
        AuthToken(
            org_id=org.id,
            user_id=user.id,
            kind=INVITE_KIND,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(hours=s.invitation_ttl_hours),
        )
    )
    db.commit()
    days = s.invitation_ttl_hours // 24
    return send_quietly(  # « Mot de passe oublié » answers the same, mail server down or not
        mailer,
        Email(
            to=user.email,
            subject=f"Créez votre accès à Pilao ({org.name})",
            body=(
                "Bonjour,\n\nVous avez demandé un nouveau mot de passe, mais votre accès n'est "
                "pas encore créé. Choisissez votre mot de passe ici "
                f"(lien valable {days} jours) :\n{s.app_base_url}/invitation?token={token}\n"
            ),
        ),
    )


def _admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "org_admin")) or 0


def change_role(db: Session, actor: Actor, user_id: uuid.UUID, role: str) -> User:
    user = colleague(db, user_id)
    if user.role == "org_admin" and role != "org_admin" and _admins(db) <= 1:
        raise ApiError(409, "last_admin", "L'entreprise doit garder au moins un administrateur.")
    user.role = role
    _audit(db, actor, "change_role", user.id)
    db.commit()
    return user


def remove(db: Session, actor: Actor, user_id: uuid.UUID) -> None:
    user = colleague(db, user_id)
    if isinstance(actor, User) and user.id == actor.id:
        raise ApiError(
            409,
            "self_removal",
            "Vous ne pouvez pas retirer votre propre accès : demandez-le à un autre "
            "administrateur.",
        )
    if user.role == "org_admin" and _admins(db) <= 1:  # only Pilao can get here
        raise ApiError(409, "last_admin", "L'entreprise doit garder au moins un administrateur.")
    _audit(db, actor, "remove_member", user.id)
    db.delete(user)  # sessions and links cascade; authorship of the work becomes empty
    db.commit()


def logout_everywhere(db: Session, actor: Actor, user_id: uuid.UUID) -> int:
    """Revoke every open session of a colleague; returns how many were open."""
    user = colleague(db, user_id)
    sessions = db.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
    ).all()
    now = _now()
    for session in sessions:
        session.revoked_at = now
    _audit(db, actor, "logout_everywhere", user.id)
    db.commit()
    return len(sessions)


# ---------- accepting (public, unscoped) ----------------------------------------------


def _valid_link(db: Session, token: str, lock: bool = False) -> tuple[AuthToken, User]:
    query = select(AuthToken).where(
        AuthToken.token_hash == hash_token(token), AuthToken.kind == INVITE_KIND
    )
    row = db.scalar(query.with_for_update() if lock else query)
    user = db.get(User, row.user_id) if row is not None else None
    if (
        row is None
        or row.used_at is not None
        or row.expires_at < _now()
        or user is None
        or user.password_hash is not None
    ):
        raise ApiError(410, "invitation_invalid", INVALID_LINK)
    if is_suspended(db.get_one(Organization, user.org_id)):
        raise suspended_error()
    return row, user


def lookup(db: Session, token: str) -> InvitationOut:
    _, user = _valid_link(db, token)
    org = db.get_one(Organization, user.org_id)
    return InvitationOut(
        email=user.email, full_name=user.full_name, org_name=org.name, role=user.role
    )


def accept(
    db: Session, data: AcceptInvitationIn, ip: str | None, user_agent: str | None
) -> tuple[str, User]:
    if not data.accept_terms:
        raise ApiError(
            422,
            "terms_required",
            "Acceptez les conditions d'utilisation et la politique de confidentialité.",
        )
    row, user = _valid_link(db, data.token, lock=True)  # single use, even concurrently
    now = _now()
    row.used_at = now
    user.full_name = data.full_name.strip()
    user.password_hash = hash_password(data.password)
    user.email_verified_at = now  # the link reached this address
    user.terms_accepted_at, user.terms_version = now, TERMS_VERSION
    db.add(
        AuditLog(
            org_id=user.org_id,
            user_id=user.id,
            action="accept_invitation",
            entity="user",
            entity_id=user.id,
        )
    )
    return open_session(db, user, ip, user_agent), user
