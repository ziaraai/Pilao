"""Dashboard rules (US-5.3): what to do now, the step of each bid, the first steps."""

import uuid
from datetime import UTC, date, datetime, timedelta

from app.domain.dashboard import BidFacts, DocFacts, actions, getting_started, progress

NOW = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)  # a Monday, 10:00 in Paris
TODAY = date(2026, 11, 9)


def bid(
    title: str = "Mairie",
    days: float | None = None,
    status: str = "in_progress",
    dce: str | None = "ready",
    analysis: str | None = "ready",
    chapters: tuple[int, int, int] | None = (0, 0, 6),
) -> BidFacts:
    return BidFacts(
        id=uuid.uuid4(),
        title=title,
        buyer_name="Ville",
        deadline_at=NOW + timedelta(days=days) if days is not None else None,
        status=status,
        dce=dce,
        analysis=analysis,
        chapters=chapters,
    )


def test_the_next_step_follows_the_dossier() -> None:
    assert progress(bid(dce=None, analysis=None, chapters=None)).next_step == "Déposer le DCE"
    reading = progress(bid(dce="processing", analysis=None, chapters=None))
    assert reading.next_step == "Lecture du DCE en cours" and reading.waiting
    assert progress(bid(dce="error", analysis=None, chapters=None)).next_step.startswith(
        "Déposer à nouveau le DCE"
    )
    assert progress(bid(analysis=None, chapters=None)).next_step == "Lancer l'analyse du DCE"
    assert progress(bid(analysis="processing", chapters=None)).waiting
    assert progress(bid(chapters=None)).next_step == "Préparer le mémoire technique"
    assert progress(bid(chapters=(2, 0, 6))).next_step == "Rédiger le mémoire (2/6 chapitres)"
    drafting = progress(bid(chapters=(2, 4, 6)))
    assert drafting.next_step == "Rédaction du mémoire en cours" and drafting.waiting
    done = progress(bid(chapters=(6, 0, 6)))
    assert done.next_step == "Relire, exporter puis déposer l'offre"
    assert done.done == ("dce", "analysis", "memoir")
    submitted = progress(bid(status="submitted", chapters=(6, 0, 6)))
    assert submitted.done == ("dce", "analysis", "memoir", "submitted")
    assert submitted.next_step is None and not submitted.waiting


def test_actions_come_by_urgency_then_date() -> None:
    bids = [
        bid("Piscine", days=30, chapters=None),
        bid("Gymnase", days=8),
        bid("Crèche", days=1.5),
        bid("Lecture", days=40, dce="processing", analysis=None, chapters=None),
        bid("Ancien", days=-2),
        bid("Déposé il y a longtemps", days=-45, status="submitted"),
        bid("Déposé récemment", days=-5, status="submitted"),
        bid("Gagné", days=-60, status="won"),
    ]
    docs = [
        DocFacts("Attestation de vigilance URSSAF", "expiring", TODAY + timedelta(days=12)),
        DocFacts("Extrait Kbis", "expired", TODAY - timedelta(days=3)),
        DocFacts("Attestation de régularité fiscale", "pending_review", None),
        DocFacts("Assurance RC", "valid", TODAY + timedelta(days=200)),
    ]
    got = actions(bids, docs, TODAY, NOW)
    assert [(a.level, a.title) for a in got] == [
        ("urgent", "Document expiré — Extrait Kbis"),
        ("urgent", "Date limite demain — Crèche"),
        ("soon", "Date limite dans 8 jours — Gymnase"),
        ("soon", "Document à renouveler — Attestation de vigilance URSSAF"),
        ("todo", "Résultat à indiquer — Déposé il y a longtemps"),
        ("todo", "Date limite passée — Ancien"),
        ("todo", "Préparer le mémoire technique — Piscine"),
        ("todo", "Document à vérifier — Attestation de régularité fiscale"),
    ]
    # a deadline line says what to do next in the dossier, and opens it
    crèche = got[1]
    assert crèche.detail == "Prochaine étape : rédiger le mémoire (0/6 chapitres)."
    assert crèche.href == f"/dossiers/{bids[2].id}" and crèche.button == "Ouvrir"
    assert got[0].href == "/coffre-fort" and got[0].button == "Remplacer"


def test_a_deadline_today_and_a_mismatched_attestation() -> None:
    today = actions([bid("Lycée", days=0.2)], [], TODAY, NOW)
    assert [a.title for a in today] == ["Date limite aujourd'hui — Lycée"]
    other = actions([], [DocFacts("Extrait Kbis", "mismatch", None)], TODAY, NOW)
    assert other[0].level == "urgent" and other[0].title == (
        "Document au nom d'une autre entreprise — Extrait Kbis"
    )


def test_the_first_steps_tick_themselves_off() -> None:
    fresh = getting_started(10, ["Attestation de vigilance URSSAF", "Extrait Kbis"], 0, 0)
    assert [(s.key, s.done) for s in fresh] == [
        ("profile", False),
        ("vault", False),
        ("knowledge", False),
        ("bid", False),
    ]
    assert fresh[0].detail == "Profil complet à 10 %."
    assert fresh[1].detail == "À ajouter : Attestation de vigilance URSSAF, Extrait Kbis."
    later = getting_started(85, [], 2, 1)
    assert all(s.done for s in later)
