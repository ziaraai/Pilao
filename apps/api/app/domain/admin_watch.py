"""« À surveiller » of the platform administration: pure rules over facts read elsewhere.

Red: an import in error or silent, a job in error or stuck, too many failed AI calls.
Amber: a company that stopped using Pilao. Red first, then the most recent.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

STUCK_AFTER = timedelta(minutes=30)  # a pending or running job older than this is stuck
IMPORT_SILENCE = timedelta(hours=6)  # the readers run every 2 hours
INACTIVE_AFTER = timedelta(days=10)
AI_MIN_CALLS = 10  # below: too few calls for a rate to mean anything
AI_MAX_FAILURE_RATE = 0.20
MAX_JOB_LINES = 10
CREDIT_LINES = 10  # lot 4: companies without credits shown by name, the others counted

# ``jobs.kind`` -> what the job does, in the words of the interface.
JOB_LABELS = {
    "process_dce": "Lecture du DCE",
    "fetch_dce": "Récupération du DCE",
    "analyze_dce": "Analyse du DCE",
    "index_knowledge_document": "Lecture d'un document",
    "read_compliance_document": "Lecture d'une attestation",
    "draft_memoir_section": "Rédaction du mémoire",
    "memoir_conformity": "Matrice de conformité",
    "export_memoir": "Export",
    "profile_prefill": "Lecture des documents du profil",
}

# ``ai_calls.task`` -> the same, for the AI costs.
TASK_LABELS = {
    "dce_extraction": "Analyse du DCE",
    "memoir_generation": "Rédaction du mémoire",
    "memoir_regeneration": "Régénération d'un chapitre",
    "settings_check": "Essai d'un modèle",  # lot 5: a model tried from the administration
    "tender_scoring": "Score des annonces",
    "profile_extraction": "Lecture des documents du profil",
    "compliance_reading": "Lecture des attestations",
    "embedding": "Indexation",
}


def job_label(kind: str) -> str:
    return JOB_LABELS.get(kind, kind)


def task_label(task: str) -> str:
    return TASK_LABELS.get(task, task)


@dataclass(frozen=True)
class ImportState:
    source: str  # ted | boamp
    enabled: bool
    last_status: str | None  # status of the latest pass: running | done | error
    last_error: str | None
    last_started_at: datetime | None
    last_success_at: datetime | None


@dataclass(frozen=True)
class JobIssue:
    kind: str
    org_id: uuid.UUID | None
    org_name: str | None
    state: Literal["error", "stuck"]
    at: datetime
    message: str | None


@dataclass(frozen=True)
class OrgActivity:
    org_id: uuid.UUID
    name: str
    created_at: datetime
    last_activity_at: datetime | None


@dataclass(frozen=True)
class WatchItem:
    level: Literal["red", "amber"]
    kind: Literal["import", "job", "ai", "inactive", "credits", "settings", "robot"]
    title: str
    detail: str | None
    at: datetime | None
    org_id: uuid.UUID | None


def _imports(now: datetime, imports: list[ImportState]) -> list[WatchItem]:
    items = []
    for imp in imports:
        if not imp.enabled:
            continue
        name = imp.source.upper()
        if imp.last_status == "error":
            title, detail, at = f"Import {name} en erreur", imp.last_error, imp.last_started_at
        elif imp.last_success_at is None:
            title, detail, at = f"Aucun import {name} réussi pour l'instant", None, None
        elif now - imp.last_success_at > IMPORT_SILENCE:
            hours = int((now - imp.last_success_at).total_seconds() // 3600)
            title = f"Aucun import {name} réussi depuis {hours} h"
            detail, at = None, imp.last_success_at
        else:
            continue
        items.append(WatchItem("red", "import", title, detail, at, None))
    return items


def _jobs(jobs: list[JobIssue]) -> tuple[list[WatchItem], int]:
    recent = sorted(jobs, key=lambda j: j.at, reverse=True)
    items = [
        WatchItem(
            "red",
            "job",
            f"{job_label(j.kind)} {'bloquée' if j.state == 'stuck' else 'en erreur'}",
            j.org_name,
            j.at,
            j.org_id,
        )
        for j in recent[:MAX_JOB_LINES]
    ]
    return items, max(0, len(recent) - MAX_JOB_LINES)


def _ai(calls: int, failures: int) -> list[WatchItem]:
    if calls < AI_MIN_CALLS or failures / calls <= AI_MAX_FAILURE_RATE:
        return []
    title = f"IA : {round(100 * failures / calls)} % d'appels en échec sur 24 heures"
    return [WatchItem("red", "ai", title, f"{failures} échecs sur {calls} appels", None, None)]


def _inactive(now: datetime, orgs: list[OrgActivity]) -> list[WatchItem]:
    items = []
    for org in orgs:
        if now - org.created_at <= INACTIVE_AFTER:
            continue  # just signed up
        if org.last_activity_at is None:
            since = "l'inscription"
        elif now - org.last_activity_at > INACTIVE_AFTER:
            since = f"{(now - org.last_activity_at).days} jours"
        else:
            continue
        title = f"{org.name} : aucune activité depuis {since}"
        items.append(WatchItem("amber", "inactive", title, None, org.last_activity_at, org.org_id))
    return items


def _robot(unreadable: int, unavailable: int) -> list[WatchItem]:
    """The DCE robot over 24 hours (spec « Récupération des DCE », § 4.5): a page it no longer
    reads means the platform changed; a platform that does not answer may only be down."""
    items = []
    if unreadable:
        title = f"Robot des DCE : {unreadable} page(s) non comprise(s) en 24 h"
        items.append(WatchItem("red", "robot", title, None, None, None))
    if unavailable:
        title = f"Robot des DCE : {unavailable} plateforme(s) sans réponse en 24 h"
        items.append(WatchItem("amber", "robot", title, None, None, None))
    return items


def watch(
    now: datetime,
    imports: list[ImportState],
    jobs: list[JobIssue],
    ai_calls: int,
    ai_failures: int,
    orgs: list[OrgActivity],
    out_of_credits: list[tuple[uuid.UUID, str]] | None = None,
    settings_alerts: list[WatchItem] | None = None,
    robot: tuple[int, int] = (0, 0),
) -> tuple[list[WatchItem], int]:
    """The lines to show, and how many job issues were left out (beyond ten). Lot 5: the
    red settings lines (an unreadable key) go with the reds, the orange ones come last."""
    job_items, more = _jobs(jobs)
    alerts = settings_alerts or []
    reds = job_items + _imports(now, imports) + _ai(ai_calls, ai_failures)
    reds += [a for a in alerts if a.level == "red"]
    reds += _robot(*robot)
    reds.sort(key=lambda i: (i.at is None, -(i.at.timestamp() if i.at else 0)))
    out = out_of_credits or []
    empty = [  # lot 4: a good moment to offer a top-up or a bigger plan
        WatchItem("amber", "credits", f"{name} n'a plus de crédits", None, None, org_id)
        for org_id, name in out[:CREDIT_LINES]
    ]
    if len(out) > CREDIT_LINES:
        n = len(out) - CREDIT_LINES
        others = "1 autre entreprise" if n == 1 else f"{n} autres entreprises"
        empty.append(WatchItem("amber", "credits", f"… et {others} sans crédits", None, None, None))
    ambers = [a for a in alerts if a.level == "amber"]
    return reds + _inactive(now, orgs) + empty + ambers, more
