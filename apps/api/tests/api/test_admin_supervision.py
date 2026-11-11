"""Supervision of the platform, read-only: overview, companies, a company's page (US-6.2)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    Feedback,
    Organization,
    PlatformAuditLog,
    TenderImport,
    User,
)
from app.routers.admin import supervision as supervision_routes
from tests.api.admin_helpers import (
    activated_admin,
    org_named,
    seed_ai_call,
    seed_bid,
    seed_export,
    seed_job,
    seed_memoir,
)
from tests.api.helpers import signed_in_client, valid_siret
from tests.conftest import Outbox

Factory = Callable[[], TestClient]


def ago(**delta: float) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


def make_quiet(db: Session, org_id: uuid.UUID, days: float) -> None:
    """As if the company had done nothing for ``days`` days."""
    db.execute(update(User).where(User.org_id == org_id).values(last_login_at=ago(days=days)))
    db.execute(update(AuditLog).where(AuditLog.org_id == org_id).values(at=ago(days=days)))


def row(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(r for r in rows if r["name"] == name)


def test_overview_counters_and_activity(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox, 1)
    signed_in_client(make_client, outbox, 2)
    one, two = org_named(db, "Entreprise 1").id, org_named(db, "Entreprise 2").id
    make_quiet(db, two, days=8)
    open_bid = seed_bid(db, one, status="to_review", minutes_with_pilao=120, minutes_usual=480)
    drafting = seed_bid(db, one, status="in_progress")
    seed_bid(db, one, status="submitted")
    seed_bid(db, two, status="won", created_at=ago(days=8))
    seed_memoir(db, open_bid, status="ready")
    seed_memoir(db, drafting, status="draft")
    seed_export(db, open_bid, kind="memoir_docx")
    seed_export(db, open_bid, kind="dc1")  # a form is not an export of the memoir
    seed_ai_call(db, one, "memoir_generation", "0.30")
    seed_ai_call(db, two, "dce_extraction", "0.20")
    seed_ai_call(db, one, "memoir_generation", "5.00", created_at=ago(days=40))
    seed_job(db, one, "analyze_dce", "error", finished_at=ago(hours=1), error="Fichier illisible.")
    seed_job(db, one, "analyze_dce", "error", finished_at=ago(hours=30))
    seed_job(db, two, "process_dce", "done", finished_at=ago(hours=1))
    db.add(TenderImport(source="ted", status="done", since=ago(days=1).date(), fetched=212))
    db.commit()
    admin, _ = activated_admin(make_client, db)

    res = admin.get("/admin/overview")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["counters"] == {
        "organizations": 2,
        "active_7d": 1,
        "bids_open": 2,
        "memoirs_done": 1,
        "ai_cost_month": "0.50",
        "job_errors_24h": 1,
    }
    assert row(body["activity"], "Entreprise 1") | {"org_id": ""} == {
        "org_id": "",
        "name": "Entreprise 1",
        "logins": 1,
        "bids": 3,
        "memoirs": 2,
        "exports": 1,
    }
    assert row(body["activity"], "Entreprise 2") | {"org_id": ""} == {
        "org_id": "",
        "name": "Entreprise 2",
        "logins": 0,
        "bids": 0,
        "memoirs": 0,
        "exports": 0,
    }
    assert [r["name"] for r in body["activity"]] == ["Entreprise 1", "Entreprise 2"]
    (issue,) = body["watch"]  # one job in error over 24 hours, the TED import is fine
    assert (issue["level"], issue["kind"]) == ("red", "job")
    assert (issue["title"], issue["detail"]) == ("Analyse du DCE en erreur", "Entreprise 1")
    assert issue["org_id"] == str(one) and body["more_job_issues"] == 0
    ted, boamp = body["imports"]
    assert (ted["source"], ted["enabled"], ted["status"], ted["fetched"]) == (
        "ted",
        True,
        "done",
        212,
    )
    assert (boamp["source"], boamp["enabled"], boamp["status"]) == ("boamp", False, None)
    assert body["time_saved"] == [
        {"name": "Entreprise 1", "bids": 1, "minutes_saved": 360, "percent": 75}
    ]


def test_stuck_jobs_and_a_silent_import_are_watched(make_client: Factory, db: Session) -> None:
    seed_job(db, None, "profile_prefill", "running", started_at=ago(minutes=31))
    seed_job(db, None, "export_memoir", "pending", created_at=ago(minutes=31))
    seed_job(db, None, "export_memoir", "running", started_at=ago(minutes=29))  # still working
    db.commit()
    admin, _ = activated_admin(make_client, db)

    body = admin.get("/admin/overview").json()

    assert sorted((i["kind"], i["title"]) for i in body["watch"]) == [
        ("import", "Aucun import TED réussi pour l'instant"),
        ("job", "Export bloquée"),
        ("job", "Lecture des documents du profil bloquée"),
    ]
    assert body["counters"]["job_errors_24h"] == 0


def test_overview_of_an_empty_platform(
    make_client: Factory, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ted_import_enabled", False)
    admin, _ = activated_admin(make_client, db)

    res = admin.get("/admin/overview")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["counters"] == {
        "organizations": 0,
        "active_7d": 0,
        "bids_open": 0,
        "memoirs_done": 0,
        "ai_cost_month": "0.00",
        "job_errors_24h": 0,
    }
    assert (body["watch"], body["more_job_issues"]) == ([], 0)
    assert (body["activity"], body["time_saved"]) == ([], [])
    assert admin.get("/admin/organizations").json() == []


def test_company_without_users_or_profile(make_client: Factory, db: Session) -> None:
    siret = valid_siret("9999999000001")
    org = Organization(siren=siret[:9], siret=siret, name="Coquille Vide")
    db.add(org)
    db.commit()
    admin, _ = activated_admin(make_client, db)

    (listed,) = admin.get("/admin/organizations").json()
    assert (listed["name"], listed["city"], listed["users"]) == ("Coquille Vide", None, 0)
    assert (listed["completeness_pct"], listed["last_activity_at"]) == (0, None)
    detail = admin.get(f"/admin/organizations/{org.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["users"] == [] and detail.json()["identity"]["trades"] == []
    assert admin.get("/admin/overview").status_code == 200


def test_list_columns_and_deletion_badge(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox, 1)
    second = signed_in_client(make_client, outbox, 2)
    one, two = org_named(db, "Entreprise 1").id, org_named(db, "Entreprise 2").id
    make_quiet(db, one, days=3)
    bid = seed_bid(db, two, status="in_progress")
    seed_memoir(db, bid, status="exported")
    seed_ai_call(db, two, "tender_scoring", "1.25")
    db.commit()
    assert (
        second.post("/organization/deletion", json={"confirmation": "Entreprise 2"}).status_code
        == 202
    )
    admin, _ = activated_admin(make_client, db)

    rows = admin.get("/admin/organizations").json()

    assert [r["name"] for r in rows] == ["Entreprise 2", "Entreprise 1"]  # last active first
    latest, older = rows
    assert latest["id"] == str(two) and latest["users"] == 1
    assert (latest["bids"], latest["memoirs"], latest["ai_cost_month"]) == (1, 1, "1.25")
    assert latest["deletion_requested"] is True and older["deletion_requested"] is False
    assert (older["bids"], older["memoirs"], older["ai_cost_month"]) == (0, 0, "0.00")
    assert datetime.fromisoformat(older["last_activity_at"]) < ago(days=2)
    assert set(latest) == {
        "id",
        "name",
        "city",
        "created_at",
        "users",
        "last_activity_at",
        "bids",
        "memoirs",
        "completeness_pct",
        "ai_cost_month",
        "deletion_requested",
        "siret",
        "suspended",
        "suspended_at",
        "suspension_reason",
        "deletion_due_at",
        "invitation_pending",
        "modules",
    }


def test_detail_and_its_audit_entry(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox, 1)
    company.put("/profile", json={"trades": ["nettoyage_locaux"], "departments": ["69", "42"]})
    assert (
        company.post("/feedback", json={"kind": "idea", "message": "Un export Excel ?"}).status_code
        == 201
    )
    one = org_named(db, "Entreprise 1")
    bid = seed_bid(db, one.id, status="to_review")
    seed_bid(db, one.id, status="won")
    seed_memoir(db, bid, status="ready")
    seed_ai_call(db, one.id, "memoir_generation", "0.40")
    seed_ai_call(db, one.id, "dce_extraction", "0.10")
    seed_ai_call(db, one.id, "memoir_generation", "2.00", created_at=ago(days=40))
    seed_job(db, one.id, "process_dce", "error", finished_at=ago(days=2), error="PDF protégé.")
    seed_job(db, one.id, "process_dce", "error", finished_at=ago(days=31))
    db.commit()
    admin, _ = activated_admin(make_client, db)

    res = admin.get(f"/admin/organizations/{one.id}")

    assert res.status_code == 200, res.text
    body = res.json()
    identity = body["identity"]
    assert (identity["name"], identity["siret"]) == ("Entreprise 1", one.siret)
    assert identity["trades"] == ["nettoyage_locaux"] and identity["departments"] == ["69", "42"]
    assert identity["deletion_requested"] is False
    (user,) = body["users"]
    assert (user["full_name"], user["email"], user["role"]) == (
        "User 1",
        "user1@example.fr",
        "org_admin",
    )
    assert user["email_verified"] is True and user["last_login_at"] is not None
    counters = body["counters"]
    assert counters["bids"] == 2 and counters["bids_by_status"] == {"to_review": 1, "won": 1}
    assert (counters["memoirs_done"], counters["ai_cost_month"]) == (1, "0.50")
    assert len(body["ai_months"]) == 6 and body["ai_months"][-1]["cost"] == "0.50"
    assert Decimal(sum(Decimal(m["cost"]) for m in body["ai_months"])) == Decimal("2.50")
    assert [(t["task"], t["label"], t["calls"], t["cost"]) for t in body["ai_tasks"]] == [
        ("memoir_generation", "Rédaction du mémoire", 1, "0.40"),
        ("dce_extraction", "Analyse du DCE", 1, "0.10"),
    ]
    (error,) = body["job_errors"]  # 30 days
    assert (error["label"], error["state"], error["message"]) == (
        "Lecture du DCE",
        "error",
        "PDF protégé.",
    )
    (note,) = body["feedback"]
    assert (note["kind"], note["message"], note["user_email"]) == (
        "idea",
        "Un export Excel ?",
        "user1@example.fr",
    )
    seen = db.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == "organization_viewed")
    ).all()
    assert [(s.org_id, s.admin_email) for s in seen] == [(one.id, "admin@pilao.test")]

    assert admin.get(f"/admin/organizations/{uuid.uuid4()}").status_code == 404
    assert admin.get("/admin/organizations/pas-un-identifiant").status_code == 422
    assert (
        len(
            db.scalars(
                select(PlatformAuditLog.id).where(PlatformAuditLog.action == "organization_viewed")
            ).all()
        )
        == 1
    )  # an unknown company leaves no trace


# --- AI costs, system, feedback -----------------------------------------------------------

FROZEN = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)  # a Tuesday noon, mid-month


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """The supervision routes believe it is ``FROZEN``: months do not move under the tests."""
    monkeypatch.setattr(supervision_routes, "_now", lambda: FROZEN)
    return FROZEN


def test_costs_by_month_company_task_and_model(
    make_client: Factory, outbox: Outbox, db: Session, frozen: datetime
) -> None:
    signed_in_client(make_client, outbox, 1)
    signed_in_client(make_client, outbox, 2)
    one, two = org_named(db, "Entreprise 1").id, org_named(db, "Entreprise 2").id
    hour_ago = frozen - timedelta(hours=1)
    seed_ai_call(
        db,
        one,
        "memoir_generation",
        "0.20",
        created_at=hour_ago,
        input_tokens=1000,
        output_tokens=500,
        latency_ms=2000,
    )
    seed_ai_call(
        db,
        one,
        "memoir_generation",
        "0.10",
        created_at=hour_ago,
        input_tokens=200,
        output_tokens=0,
        latency_ms=4000,
        success=False,
    )
    seed_ai_call(db, two, "dce_extraction", "0.25", created_at=hour_ago)
    seed_ai_call(db, None, "tender_scoring", "0.05", created_at=hour_ago)
    seed_ai_call(
        db, one, "memoir_generation", "9.00", created_at=datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    )
    db.commit()
    admin, _ = activated_admin(make_client, db)

    res = admin.get("/admin/ai-costs")

    assert res.status_code == 200, res.text
    r = res.json()
    assert (r["month"], r["total"]) == ("2026-11", "0.60")
    assert r["months"][:2] == ["2026-11", "2026-10"] and r["months"][-1] == "2025-12"
    assert len(r["months"]) == 12
    assert [(o["name"], o["calls"], o["cost"]) for o in r["by_org"]] == [
        ("Entreprise 1", 2, "0.30"),
        ("Entreprise 2", 1, "0.25"),
        ("Plateforme", 1, "0.05"),
    ]
    first, _, platform = r["by_org"]
    assert (first["org_id"], first["input_tokens"], first["output_tokens"]) == (
        str(one),
        1200,
        500,
    )
    assert platform["org_id"] is None
    assert r["by_task"][0] == {
        "task": "memoir_generation",
        "label": "Rédaction du mémoire",
        "calls": 2,
        "failures": 1,
        "avg_latency_ms": 3000,
        "cost": "0.30",
    }
    assert [t["task"] for t in r["by_task"]] == [
        "memoir_generation",
        "dce_extraction",
        "tender_scoring",
    ]
    assert r["by_model"] == [{"model": "fournisseur/modele", "calls": 4, "cost": "0.60"}]
    october = admin.get("/admin/ai-costs", params={"month": "2026-10"}).json()
    assert (october["month"], october["total"]) == ("2026-10", "9.00")


def test_month_edge_in_paris_time(make_client: Factory, db: Session, frozen: datetime) -> None:
    # 31 October 23:30 UTC is already 1 November, 00:30, in Paris
    seed_ai_call(
        db, None, "embedding", "1.00", created_at=datetime(2026, 10, 31, 23, 30, tzinfo=UTC)
    )
    db.commit()
    admin, _ = activated_admin(make_client, db)
    assert admin.get("/admin/ai-costs", params={"month": "2026-11"}).json()["total"] == "1.00"
    assert admin.get("/admin/ai-costs", params={"month": "2026-10"}).json()["total"] == "0.00"


def test_bad_month(make_client: Factory, db: Session, frozen: datetime) -> None:
    admin, _ = activated_admin(make_client, db)
    for month in ("2026-13", "novembre", "2025-11", "2026-12", "2026-1"):
        assert admin.get("/admin/ai-costs", params={"month": month}).status_code == 422, month
    assert admin.get("/admin/ai-costs", params={"month": "2025-12"}).status_code == 200


def test_system_lists_imports_and_job_issues(
    make_client: Factory, outbox: Outbox, db: Session, frozen: datetime
) -> None:
    signed_in_client(make_client, outbox, 1)
    one = org_named(db, "Entreprise 1").id
    start = frozen - timedelta(hours=2)
    db.add(
        TenderImport(
            source="ted",
            status="done",
            since=start.date(),
            created_at=start,
            finished_at=start + timedelta(minutes=1),
            fetched=212,
            created=14,
            updated=3,
            corrected=1,
            skipped=2,
            matched=9,
        )
    )
    db.add(
        TenderImport(
            source="boamp",
            status="error",
            since=start.date(),
            created_at=frozen - timedelta(hours=1),
            error="le site n'a pas répondu",
        )
    )
    seed_job(
        db,
        one,
        "analyze_dce",
        "error",
        finished_at=frozen - timedelta(days=2),
        error="Fichier illisible.",
    )
    seed_job(db, one, "draft_memoir_section", "running", started_at=frozen - timedelta(minutes=31))
    seed_job(db, one, "process_dce", "done", finished_at=frozen - timedelta(hours=1))
    seed_job(db, one, "process_dce", "error", finished_at=frozen - timedelta(days=31))
    db.commit()
    admin, _ = activated_admin(make_client, db)

    res = admin.get("/admin/system")

    assert res.status_code == 200, res.text
    body = res.json()
    boamp, ted = body["imports"]  # the most recent first
    assert (boamp["source"], boamp["status"], boamp["error"]) == (
        "boamp",
        "error",
        "le site n'a pas répondu",
    )
    assert boamp["duration_seconds"] is None
    assert ted == {
        "source": "ted",
        "status": "done",
        "started_at": start.isoformat().replace("+00:00", "Z"),
        "duration_seconds": 60,
        "fetched": 212,
        "created": 14,
        "updated": 3,
        "corrected": 1,
        "skipped": 2,
        "matched": 9,
        "error": None,
    }
    stuck, failed = body["jobs"]  # 30 days, the most recent first
    assert (stuck["label"], stuck["state"], stuck["message"]) == (
        "Rédaction du mémoire",
        "stuck",
        None,
    )
    assert (failed["label"], failed["state"], failed["message"], failed["org_name"]) == (
        "Analyse du DCE",
        "error",
        "Fichier illisible.",
        "Entreprise 1",
    )


def test_feedback_window_and_time_saved(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox, 1)
    for kind, message in (("problem", "Le PDF ne s'ouvre pas."), ("idea", "Un export Excel ?")):
        sent = company.post(
            "/feedback", json={"kind": kind, "message": message, "page": "/dossiers"}
        )
        assert sent.status_code == 201
    one = org_named(db, "Entreprise 1").id
    db.execute(update(Feedback).where(Feedback.kind == "problem").values(created_at=ago(days=40)))
    db.execute(update(Feedback).where(Feedback.kind == "idea").values(created_at=ago(days=5)))
    seed_bid(db, one, minutes_with_pilao=60, minutes_usual=240)
    db.commit()
    admin, _ = activated_admin(make_client, db)

    week = admin.get("/admin/feedback", params={"days": 7}).json()
    assert week["days"] == 7
    (note,) = week["items"]
    assert note | {"created_at": ""} == {
        "created_at": "",
        "org_name": "Entreprise 1",
        "user_email": "user1@example.fr",
        "kind": "idea",
        "page": "/dossiers",
        "message": "Un export Excel ?",
    }
    assert week["time_saved"] == [
        {"name": "Entreprise 1", "bids": 1, "minutes_saved": 180, "percent": 75}
    ]
    default = admin.get("/admin/feedback").json()
    assert default["days"] == 30 and len(default["items"]) == 1
    quarter = admin.get("/admin/feedback", params={"days": 90}).json()
    assert [i["kind"] for i in quarter["items"]] == ["idea", "problem"]
    assert admin.get("/admin/feedback", params={"days": 15}).status_code == 422


def test_a_stuck_job_that_was_retried_or_is_too_old_is_not_shown(
    make_client: Factory, db: Session, frozen: datetime
) -> None:
    """A worker killed mid-job leaves its row « running » for good: only the latest job of a
    piece of work counts, and only over the window of the screen."""
    retried, current = uuid.uuid4(), uuid.uuid4()
    long_ago = frozen - timedelta(days=31)
    # left running by a worker killed during a deploy, then relaunched and finished
    seed_job(
        db,
        None,
        "analyze_dce",
        "running",
        ref_id=retried,
        started_at=frozen - timedelta(hours=5),
        created_at=frozen - timedelta(hours=5),
    )
    seed_job(
        db,
        None,
        "analyze_dce",
        "done",
        ref_id=retried,
        created_at=frozen - timedelta(hours=4),
        finished_at=frozen - timedelta(hours=4),
    )
    # stuck for weeks: out of the 30 days of the screen
    seed_job(db, None, "export_memoir", "pending", ref_id=uuid.uuid4(), created_at=long_ago)
    # really stuck now
    seed_job(
        db,
        None,
        "profile_prefill",
        "running",
        ref_id=current,
        started_at=frozen - timedelta(minutes=45),
        created_at=frozen - timedelta(minutes=45),
    )
    db.commit()
    admin, _ = activated_admin(make_client, db)

    jobs = admin.get("/admin/system").json()["jobs"]
    assert [(j["kind"], j["state"]) for j in jobs] == [("profile_prefill", "stuck")]
    watched = [
        i["title"] for i in admin.get("/admin/overview").json()["watch"] if i["kind"] == "job"
    ]
    assert watched == ["Lecture des documents du profil bloquée"]
