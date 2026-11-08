"""Dashboard rules (US-5.3): what to do now, the step of each bid, the first steps.

Pure functions over plain facts: ``services/dashboard.py`` gathers them from the database,
the tests feed them directly. Texts are in French, ready to show.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
LEVELS = ("urgent", "soon", "todo")
URGENT_DAYS, SOON_DAYS = 3, 10  # deadline within: red, orange
RESULT_AFTER_DAYS = 30  # a submitted offer usually has its result by then
STAGES = ("dce", "analysis", "memoir", "submitted")
OPEN = ("to_review", "in_progress")
MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


@dataclass(frozen=True)
class BidFacts:
    id: uuid.UUID
    title: str
    buyer_name: str | None
    deadline_at: datetime | None
    status: str
    dce: str | None  # status of the latest DCE version, None before the first deposit
    analysis: str | None  # status of the latest analysis
    chapters: tuple[int, int, int] | None  # latest memoir: (drafted, drafting, total)


@dataclass(frozen=True)
class Progress:
    done: tuple[str, ...]  # stages done, in STAGES order
    next_step: str | None  # None once the offer is submitted
    waiting: bool  # Pilao is working on it: nothing to do but wait


@dataclass(frozen=True)
class DocFacts:
    label: str  # « Extrait Kbis »
    status: str  # valid, expiring, expired, mismatch, pending_review
    valid_until: date | None


@dataclass(frozen=True)
class Action:
    level: str  # urgent, soon, todo
    title: str
    detail: str | None
    href: str
    button: str
    due: date | None


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    detail: str
    href: str
    done: bool


def progress(b: BidFacts) -> Progress:
    drafted, drafting, total = b.chapters or (0, 0, 0)
    stages = {
        "dce": b.dce == "ready",
        "analysis": b.analysis == "ready",
        "memoir": total > 0 and drafted >= total,
        "submitted": b.status in ("submitted", "won", "lost"),
    }
    done = tuple(s for s in STAGES if stages[s])
    if b.status not in OPEN:
        return Progress(done, None, False)
    step, waiting = _next(b, drafted, drafting, total)
    return Progress(done, step, waiting)


def _next(b: BidFacts, drafted: int, drafting: int, total: int) -> tuple[str, bool]:
    if b.dce is None:
        return "Déposer le DCE", False
    if b.dce in ("pending", "processing"):
        return "Lecture du DCE en cours", True
    if b.dce == "error":
        return "Déposer à nouveau le DCE (lecture impossible)", False
    if b.analysis is None:
        return "Lancer l'analyse du DCE", False
    if b.analysis in ("pending", "processing"):
        return "Analyse du DCE en cours", True
    if b.analysis == "error":
        return "Relancer l'analyse du DCE", False
    if b.chapters is None:
        return "Préparer le mémoire technique", False
    if drafting:
        return "Rédaction du mémoire en cours", True
    if drafted < total:
        return f"Rédiger le mémoire ({drafted}/{total} chapitres)", False
    return "Relire, exporter puis déposer l'offre", False


def french_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def _in_days(n: int) -> str:
    return "aujourd'hui" if n == 0 else "demain" if n == 1 else f"dans {n} jours"


def actions(bids: list[BidFacts], docs: list[DocFacts], today: date, now: datetime) -> list[Action]:
    """Everything to do, most urgent first, then by date."""
    found = [a for b in bids if (a := _bid_action(b, today, now))]
    found += [a for d in docs if (a := _doc_action(d, today))]
    return sorted(found, key=lambda a: (LEVELS.index(a.level), a.due or date.max, a.title))


def _bid_action(b: BidFacts, today: date, now: datetime) -> Action | None:
    href = f"/dossiers/{b.id}"
    due = b.deadline_at.astimezone(PARIS).date() if b.deadline_at else None
    if b.status == "submitted" and b.deadline_at and due:
        if b.deadline_at <= now - timedelta(days=RESULT_AFTER_DAYS):
            return Action(
                "todo",
                f"Résultat à indiquer — {b.title}",
                f"Offre déposée, date limite le {french_date(due)} : gagné ou perdu ?",
                href,
                "Indiquer",
                due,
            )
        return None
    if b.status not in OPEN:
        return None
    p = progress(b)
    if b.deadline_at and due:
        if b.deadline_at < now:
            return Action(
                "todo",
                f"Date limite passée — {b.title}",
                "Indiquez si l'offre a été déposée ou abandonnée.",
                href,
                "Mettre à jour",
                due,
            )
        days = (due - today).days
        if days <= SOON_DAYS:
            step = p.next_step or ""
            return Action(
                "urgent" if days <= URGENT_DAYS else "soon",
                f"Date limite {_in_days(days)} — {b.title}",
                f"Prochaine étape : {step[:1].lower()}{step[1:]}." if step else None,
                href,
                "Ouvrir",
                due,
            )
    if p.waiting or not p.next_step:
        return None
    return Action(
        "todo",
        f"{p.next_step} — {b.title}",
        f"Date limite le {french_date(due)}." if due else None,
        href,
        "Continuer",
        due,
    )


def _doc_action(d: DocFacts, today: date) -> Action | None:
    until = f"Fin de validité le {french_date(d.valid_until)}" if d.valid_until else None
    if d.status == "expired":
        return Action(
            "urgent",
            f"Document expiré — {d.label}",
            f"{until} : il n'est plus joint aux exports." if until else None,
            "/coffre-fort",
            "Remplacer",
            d.valid_until,
        )
    if d.status == "mismatch":
        return Action(
            "urgent",
            f"Document au nom d'une autre entreprise — {d.label}",
            "Le SIREN ne correspond pas : déposez le bon document.",
            "/coffre-fort",
            "Remplacer",
            d.valid_until,
        )
    if d.status == "expiring":
        days = (d.valid_until - today).days if d.valid_until else None
        return Action(
            "soon",
            f"Document à renouveler — {d.label}",
            f"{until} ({_in_days(days)})." if until and days is not None else until,
            "/coffre-fort",
            "Renouveler",
            d.valid_until,
        )
    if d.status == "pending_review":
        return Action(
            "todo",
            f"Document à vérifier — {d.label}",
            "Confirmez les dates lues par Pilao.",
            "/coffre-fort",
            "Vérifier",
            None,
        )
    return None


def getting_started(
    profile_pct: int, missing_docs: list[str], knowledge_docs: int, bids: int
) -> list[Step]:
    """The 4 first steps of a new account; each is ticked off by what it asks for."""
    return [
        Step(
            "profile",
            "Compléter le profil de l'entreprise",
            f"Profil complet à {profile_pct} %.",
            "/profil",
            profile_pct >= 80,
        ),
        Step(
            "vault",
            "Ajouter vos attestations",
            f"À ajouter : {', '.join(missing_docs)}." if missing_docs else "Attestations à jour.",
            "/coffre-fort",
            not missing_docs,
        ),
        Step(
            "knowledge",
            "Déposer un ancien mémoire technique",
            "Pilao reprend votre plan et votre façon d'écrire.",
            "/documents",
            knowledge_docs > 0,
        ),
        Step(
            "bid",
            "Créer votre premier dossier",
            "Déposez le DCE d'un appel d'offres : Pilao l'analyse.",
            "/dossiers",
            bids > 0,
        ),
    ]
