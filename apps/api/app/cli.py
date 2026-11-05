"""Command line tools: ``uv run python -m app.cli <command>``.

* ``load-tenders notices.json`` loads notices already in the normalized format
  (``TenderIn``), the same path the BOAMP and TED importers take: upsert, corrections,
  duplicates, then matching for every company (the scoring runs in the worker).
* ``eval-models --models a,b,c`` runs the phase 0 comparison (docs/11) on ``samples/``:
  every DCE through the real pipeline with each model, then the anonymized memoirs, the
  rating grid and the cost report. Never on the production database.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.email import get_mailer
from app.db.session import get_sessionmaker
from app.schemas.tenders import TenderIn
from app.services.tenders import ingest, match_tenders
from app.workers.queue import get_job_queue


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
    args = parser.parse_args(argv)
    if args.command == "eval-models":
        return eval_models(args)

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
