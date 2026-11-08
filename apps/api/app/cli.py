"""Command line tools: ``uv run python -m app.cli <command>``.

* ``load-tenders notices.json`` loads notices already in the normalized format
  (``TenderIn``), the same path the BOAMP and TED importers take: upsert, corrections,
  duplicates, then matching for every company (the scoring runs in the worker).
* ``feedback-report [--days 30] [--csv retours.csv]``: what the testers wrote from the
  application, and the time saved per company (P4-02). Read-only, every company.
* ``send-test-email you@example.fr``: checks the outgoing e-mail settings (SMTP).
* ``import-tenders [--source ted|boamp] [--since 2026-10-01] [--essai]``: one pass of the
  notice readers now (as the scheduler does every 2 hours). ``--essai`` reads and shows a
  few notices without saving anything: the check of a reader from the server.
* ``eval-models --models a,b,c`` runs the phase 0 comparison (docs/11) on ``samples/``:
  every DCE through the real pipeline with each model, then the anonymized memoirs, the
  rating grid and the cost report. Never on the production database.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.email import get_mailer
from app.db.session import get_sessionmaker
from app.schemas.tenders import TenderIn
from app.services.tenders import ingest, match_tenders
from app.workers.queue import get_job_queue

PARIS = ZoneInfo("Europe/Paris")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("load-tenders", help="charger des annonces (JSON normalisé)")
    load.add_argument("path", type=Path)
    ev = commands.add_parser("eval-models", help="phase 0 : comparer des modèles d'IA")
    ev.add_argument("--models", required=True, help="noms LiteLLM séparés par des virgules")
    ev.add_argument("--samples", type=Path, default=Path("../../samples"))
    ev.add_argument("--out", type=Path, default=Path("../../samples/resultats"))
    ev.add_argument("--seed", type=int, default=None, help="tirage des lettres reproductible")
    ev.add_argument(
        "--any-database",
        action="store_true",
        help="accepter une base dont le nom ne finit pas par _eval",
    )
    fb = commands.add_parser("feedback-report", help="retours des utilisateurs, temps gagné")
    fb.add_argument("--days", type=int, default=30)
    fb.add_argument("--csv", type=Path, default=None, help="écrire aussi les avis en CSV")
    mail = commands.add_parser("send-test-email", help="vérifier l'envoi des e-mails (SMTP)")
    mail.add_argument("to")
    imp = commands.add_parser("import-tenders", help="importer les annonces BOAMP / TED")
    imp.add_argument("--source", choices=["ted", "boamp"], default=None)
    imp.add_argument("--since", type=date.fromisoformat, default=None, help="AAAA-MM-JJ")
    imp.add_argument("--essai", action="store_true", help="lire sans rien enregistrer")
    imp.add_argument("--limit", type=int, default=None, help="nombre d'annonces lues au plus")
    args = parser.parse_args(argv)
    if args.command == "send-test-email":
        return send_test_email(args.to)
    if args.command == "eval-models":
        return eval_models(args)
    if args.command == "feedback-report":
        return feedback_report(args)
    if args.command == "import-tenders":
        return import_tenders(args)

    items = [TenderIn.model_validate(x) for x in json.loads(args.path.read_text("utf-8"))]
    with get_sessionmaker()() as db:  # unscoped: notices are global
        report = ingest(db, items, get_mailer())
        matched = match_tenders(db, report.to_match, get_job_queue())
    print(
        f"{report.created} créée(s), {report.updated} mise(s) à jour, "
        f"{report.corrected} rectifiée(s), {report.duplicates} doublon(s), "
        f"{report.awards} attribution(s), {report.unchanged} inchangée(s) ; "
        f"{matched} correspondance(s) avec les entreprises."
    )
    return 0


def import_tenders(args: argparse.Namespace) -> int:
    from app.integrations.boamp import BoampReader
    from app.integrations.ted import TedReader
    from app.services.tender_import import Reader, Source, describe, next_since, run_import

    sources = [args.source] if args.source else ["ted", "boamp"]
    makers: dict[str, type[Reader]] = {"ted": TedReader, "boamp": BoampReader}
    limit = args.limit if args.limit is not None else (3 if args.essai else None)
    failed = False
    with get_sessionmaker()() as db:  # unscoped: notices are global
        for source in sources:
            reader = makers[source]()
            if args.essai and isinstance(reader, BoampReader):  # what the real data holds
                since = args.since or next_since(db, source, date.today())
                try:
                    probe = reader.probe(since)
                except Exception as exc:  # noqa: BLE001 - shown, the import below says more
                    print(f"BOAMP : lecture impossible ({exc}).")
                else:
                    print("BOAMP, champs du jeu de données :", ", ".join(probe["fields"]))
                    print("BOAMP, un avis réel :", probe["record"])
                    print("BOAMP, début de « donnees » :", probe["donnees"])
            result = run_import(
                db,
                cast(Source, source),
                reader,
                get_mailer(),
                get_job_queue(),
                since=args.since,
                dry_run=args.essai,
                limit=limit,
            )
            failed = failed or result.status == "error"
            print(describe(result))
            for t in result.samples:
                print(_sample(t))
    return 1 if failed else 0


def _sample(t: TenderIn) -> str:
    """One notice as read, for the server check of a reader (``--essai``)."""
    deadline = f"{t.deadline_at:%d/%m/%Y %H:%M}" if t.deadline_at else "?"
    return (
        f"  - {t.title[:90]}\n"
        f"    {t.buyer_name or 'acheteur ?'} · départements {', '.join(t.departments) or '?'}"
        f" · date limite {deadline} · CPV {', '.join(t.cpv_codes[:3]) or '?'}\n"
        f"    {t.notice_url or 'pas de lien'}"
    )


def send_test_email(to: str) -> int:
    from app.core.email import Email
    from app.core.errors import ApiError

    s = get_settings()
    try:
        get_mailer().send(
            Email(
                to=to,
                subject="Pilao — e-mail de test",
                body=(
                    "Bonjour,\n\nCet e-mail confirme que Pilao peut envoyer des messages "
                    f"depuis {s.app_base_url} (serveur SMTP : {s.smtp_host or 'aucun'}).\n"
                ),
            )
        )
    except ApiError as exc:
        print(f"Échec : {exc.message} Voir les journaux ci-dessus.", file=sys.stderr)
        return 1
    print(f"Envoyé à {to} par {s.smtp_host or 'la console (aucun SMTP configuré)'}.")
    return 0


def _duration(minutes: int) -> str:
    """As the application shows it: 45 min, 6 h, 5 h 30."""
    if abs(minutes) < 60:
        return f"{minutes} min"
    hours, rest = divmod(abs(minutes), 60)
    sign = "-" if minutes < 0 else ""
    return f"{sign}{hours} h {rest:02d}" if rest else f"{sign}{hours} h"


def feedback_report(args: argparse.Namespace) -> int:
    import csv
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from app.db.models import Bid, Feedback, Organization, User
    from app.services.feedback import KINDS

    since = datetime.now(UTC) - timedelta(days=args.days)
    with get_sessionmaker()() as db:  # unscoped: the team reads every company's feedback
        rows = db.execute(
            select(Feedback, Organization.name, User.email)
            .join(Organization, Organization.id == Feedback.org_id)
            .outerjoin(User, User.id == Feedback.user_id)
            .where(Feedback.created_at >= since)
            .order_by(Feedback.created_at.desc())
        ).all()
        saved = db.execute(
            select(
                Organization.name,
                func.count(),
                func.sum(Bid.minutes_with_pilao),
                func.sum(Bid.minutes_usual),
            )
            .join(Organization, Organization.id == Bid.org_id)
            .where(Bid.minutes_with_pilao.is_not(None), Bid.minutes_usual.is_not(None))
            .group_by(Organization.name)
            .order_by(Organization.name)
        ).all()
    print(f"{len(rows)} avis depuis {args.days} jour{'s' if args.days > 1 else ''}")
    for item, org, email in rows:
        when = item.created_at.astimezone(PARIS).strftime("%d/%m %H:%M")
        print(f"\n[{when}] {KINDS[item.kind]} — {org} — {email or 'compte supprimé'}")
        print(f"  page : {item.page or '?'}")
        print("  " + item.message.replace("\n", "\n  "))
    print("\nTemps gagné (dossiers où les deux durées sont saisies)")
    for org, count, with_, usual in saved:
        gain = (usual or 0) - (with_ or 0)
        pct = f" ({round(100 * gain / usual)} %)" if usual else ""
        print(f"  {org} : {count} dossier(s), {_duration(gain)} gagnées{pct}")
    if not saved:
        print("  (aucun dossier renseigné)")
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8-sig") as fh:  # opens in Excel
            out = csv.writer(fh, delimiter=";")
            out.writerow(["date", "entreprise", "utilisateur", "type", "page", "message"])
            for item, org, email in rows:
                out.writerow(
                    [
                        item.created_at.astimezone(PARIS).isoformat(timespec="minutes"),
                        org,
                        email or "",
                        KINDS[item.kind],
                        item.page or "",
                        item.message,
                    ]
                )
        print(f"\nCSV : {args.csv}")
    return 0


def eval_models(args: argparse.Namespace) -> int:
    settings = get_settings()
    database = make_url(settings.database_url).database or ""
    if settings.environment == "production":
        print("Refusé : l'évaluation ne tourne jamais en production.", file=sys.stderr)
        return 2
    if not database.endswith("_eval") and not args.any_database:
        print(
            f"Refusé : la base « {database} » ne finit pas par _eval. Créez une base dédiée "
            "(createdb pilao_eval, puis alembic upgrade head) ou passez --any-database.",
            file=sys.stderr,
        )
        return 2
    from app.core.logging import configure_logging
    from app.documents.ocr import get_ocr_engine
    from app.evaluation import run_evaluation

    configure_logging()  # one line per run: the evaluation takes minutes per model

    names = [m.strip() for m in args.models.split(",") if m.strip()]
    runs = run_evaluation(
        args.samples, names, args.out, get_sessionmaker(), get_ocr_engine(), args.seed
    )
    failed = [r for r in runs if r.error]
    print(
        f"{len(runs)} mémoire(s) produits dans {args.out} ({len(failed)} en échec). "
        "À envoyer au noteur : les dossiers des DCE et grille-de-notation.xlsx ; à garder : "
        "correspondance-a-garder.json et rapport.md."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
