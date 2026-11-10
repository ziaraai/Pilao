"""« À surveiller » of the administration: each rule, triggered and not."""

import uuid
from datetime import UTC, datetime, timedelta

from app.domain.admin_watch import (
    TASK_LABELS,
    ImportState,
    JobIssue,
    OrgActivity,
    job_label,
    watch,
)

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def ago(**delta: float) -> datetime:
    return NOW - timedelta(**delta)


def job(n: int, state: str = "error", kind: str = "analyze_dce") -> JobIssue:
    return JobIssue(kind, uuid.uuid4(), "Nettoyage Atlas", state, ago(minutes=n), "message")  # type: ignore[arg-type]


def company(name: str, created_days: float, active_days: float | None) -> OrgActivity:
    last = None if active_days is None else ago(days=active_days)
    return OrgActivity(uuid.uuid4(), name, ago(days=created_days), last)


def test_import_in_error_or_silent() -> None:
    err = ImportState("boamp", True, "error", "le site n'a pas répondu", ago(hours=1), ago(hours=3))
    silent = ImportState("ted", True, "done", None, ago(hours=7), ago(hours=7))
    never = ImportState("ted", True, None, None, None, None)
    fine = ImportState("ted", True, "done", None, ago(hours=1), ago(hours=1))
    off = ImportState("boamp", False, "error", "peu importe", ago(hours=1), None)

    items, more = watch(NOW, [err], [], 0, 0, [])
    assert [(i.level, i.kind, i.title, i.detail) for i in items] == [
        ("red", "import", "Import BOAMP en erreur", "le site n'a pas répondu")
    ]
    assert more == 0
    (late,) = watch(NOW, [silent], [], 0, 0, [])[0]
    assert (late.level, late.title) == ("red", "Aucun import TED réussi depuis 7 h")
    (none,) = watch(NOW, [never], [], 0, 0, [])[0]
    assert (none.level, none.title) == ("red", "Aucun import TED réussi pour l'instant")
    assert watch(NOW, [fine, off], [], 0, 0, []) == ([], 0)


def test_job_lines_are_capped() -> None:
    jobs = [job(n) for n in range(1, 12)] + [job(0, state="stuck", kind="draft_memoir_section")]
    items, more = watch(NOW, [], jobs, 0, 0, [])
    assert len(items) == 10 and more == 2
    assert all(i.level == "red" and i.kind == "job" for i in items)
    assert items[0].title == "Rédaction du mémoire bloquée"  # the most recent first
    assert items[1].title == "Analyse du DCE en erreur"
    assert items[1].detail == "Nettoyage Atlas" and items[1].org_id == jobs[0].org_id


def test_ai_failure_rate() -> None:
    (item,) = watch(NOW, [], [], 10, 3, [])[0]
    assert (item.level, item.kind) == ("red", "ai")
    assert item.title == "IA : 30 % d'appels en échec sur 24 heures"
    assert item.detail == "3 échecs sur 10 appels"
    assert watch(NOW, [], [], 9, 9, []) == ([], 0)  # too few calls to tell
    assert watch(NOW, [], [], 10, 2, []) == ([], 0)  # 20 % is still fine


def test_inactive_company() -> None:
    quiet = company("Vitres & Co", created_days=30, active_days=11)
    never = company("Bâti Rénov", created_days=11, active_days=None)
    new = company("Clair Services", created_days=9, active_days=None)
    busy = company("Propreté Démo", created_days=30, active_days=9)
    items, _ = watch(NOW, [], [], 0, 0, [quiet, never, new, busy])
    assert [(i.level, i.kind, i.title) for i in items] == [
        ("amber", "inactive", "Vitres & Co : aucune activité depuis 11 jours"),
        ("amber", "inactive", "Bâti Rénov : aucune activité depuis l'inscription"),
    ]
    assert items[0].org_id == quiet.org_id


def test_red_first_then_most_recent() -> None:
    quiet = company("Vitres & Co", created_days=30, active_days=11)
    err = ImportState("ted", True, "error", "panne", ago(hours=5), None)
    items, _ = watch(NOW, [err], [job(90), job(10)], 10, 5, [quiet])
    assert [(i.level, i.kind) for i in items] == [
        ("red", "job"),  # 10 minutes ago
        ("red", "job"),  # 90 minutes ago
        ("red", "import"),  # 5 hours ago
        ("red", "ai"),  # undated: after the dated ones
        ("amber", "inactive"),
    ]


def test_labels() -> None:
    assert job_label("draft_memoir_section") == "Rédaction du mémoire"
    assert job_label("process_dce") == "Lecture du DCE"
    assert job_label("inconnu") == "inconnu"  # an unknown kind is shown as it is
    assert TASK_LABELS["memoir_generation"] == "Rédaction du mémoire"
    assert set(TASK_LABELS) == {
        "dce_extraction",
        "memoir_generation",
        "tender_scoring",
        "profile_extraction",
        "compliance_reading",
        "embedding",
    }
