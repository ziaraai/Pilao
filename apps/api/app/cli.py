"""Command line tools: ``uv run python -m app.cli load-tenders notices.json``.

``load-tenders`` loads notices already in the normalized format (``TenderIn``), the same
path the BOAMP and TED importers take: upsert, corrections, duplicates, then matching for
every company (the scoring runs in the worker).
"""

import argparse
import json
import sys
from pathlib import Path

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
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
