"""`python -m app.cli admin-access`: the only way to create, reset or close a super admin."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session

from app import cli
from app.core.security import hash_password, hash_token
from app.db.models import PlatformAdmin, PlatformAdminSession, PlatformAuditLog
from tests.conftest import _new_session

EMAIL = "faycal@exemple.fr"


@pytest.fixture(autouse=True)
def _cli_on_the_test_connection(conn: Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: lambda: _new_session(conn))


def link_token(out: str) -> str:
    return out.split("jeton=")[1].split()[0]


def test_creates_the_account_and_prints_a_one_time_link(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["admin-access", "Faycal@Exemple.fr", "--name", "Faycal"]) == 0
    out = capsys.readouterr().out
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None
    assert admin.email == EMAIL and admin.full_name == "Faycal"
    # only the fingerprint of the link is stored
    assert admin.setup_token_hash == hash_token(link_token(out)) != link_token(out)
    assert admin.setup_expires_at is not None
    left = admin.setup_expires_at - datetime.now(UTC)
    assert timedelta(minutes=29) < left <= timedelta(minutes=30)
    assert "/admin/activation?jeton=" in out and "30 minutes" in out
    assert db.scalar(select(PlatformAuditLog.action)) == "access_reset"
    assert db.scalar(select(PlatformAuditLog.admin_email)) == EMAIL


def test_running_it_again_resets_the_access(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["admin-access", EMAIL, "--name", "Faycal"]) == 0
    first = link_token(capsys.readouterr().out)
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None
    # the account as it is once activated
    admin.password_hash = hash_password("un-mot-de-passe-long")
    admin.totp_secret_enc, admin.totp_confirmed_at = "chiffre", datetime.now(UTC)
    admin.totp_last_step, admin.recovery_codes = 12, ["a" * 64]
    admin.setup_token_hash = admin.setup_expires_at = None
    session = PlatformAdminSession(
        admin_id=admin.id,
        token_hash="b" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=12),
    )
    db.add(session)
    db.commit()

    assert cli.main(["admin-access", EMAIL]) == 0
    second = link_token(capsys.readouterr().out)
    db.expire_all()
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None
    assert (admin.password_hash, admin.totp_secret_enc, admin.totp_confirmed_at) == (
        None,
        None,
        None,
    )
    assert (admin.totp_last_step, admin.recovery_codes) == (None, [])
    assert admin.full_name == "Faycal"  # kept when --name is not given
    assert second != first and admin.setup_token_hash == hash_token(second)
    assert db.get_one(PlatformAdminSession, session.id).revoked_at is not None
    assert db.scalar(select(func.count()).select_from(PlatformAdmin)) == 1


def test_disable(db: Session, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["admin-access", EMAIL]) == 0
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None
    session = PlatformAdminSession(
        admin_id=admin.id,
        token_hash="c" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=12),
    )
    db.add(session)
    db.commit()
    capsys.readouterr()

    assert cli.main(["admin-access", EMAIL, "--disable"]) == 0
    assert f"Compte fermé : {EMAIL}" in capsys.readouterr().out
    db.expire_all()
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None
    assert admin.disabled_at is not None and admin.setup_token_hash is None
    assert db.get_one(PlatformAdminSession, session.id).revoked_at is not None
    actions = db.scalars(select(PlatformAuditLog.action).order_by(PlatformAuditLog.at)).all()
    assert list(actions) == ["access_reset", "disabled"]

    assert cli.main(["admin-access", "inconnu@exemple.fr", "--disable"]) == 1
    assert "Compte inconnu : inconnu@exemple.fr" in capsys.readouterr().out
    assert db.scalar(select(func.count()).select_from(PlatformAdmin)) == 1


def test_granting_access_again_reopens_a_closed_account(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["admin-access", EMAIL])
    cli.main(["admin-access", EMAIL, "--disable"])
    assert cli.main(["admin-access", EMAIL]) == 0
    db.expire_all()
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None and admin.disabled_at is None and admin.setup_token_hash


def test_a_mistyped_address_creates_nothing(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["admin-access", "pas-une-adresse"]) == 1
    assert "Adresse e-mail invalide" in capsys.readouterr().out
    assert db.scalar(select(func.count()).select_from(PlatformAdmin)) == 0
