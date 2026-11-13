"""A fake Atexo platform (PLACE-like) for the robot's tests and the browser journey.

Same pages, field names and steps as the real ones seen on 2026-11-13 (spec « Récupération des
DCE », § 2): consultation page (size, deadline), download request form (anonymous or identified,
terms), « Téléchargement complet » page whose link posts a form, then the ZIP.

Scenarios by consultation number: 1001 ZIP, 1002 closed, 1003 captcha, 1004 « 738 Mo »,
1005 page without a form, 1006 the identification is refused. Run it alone with
``python -m tests.fixtures.fake_atexo --port 8765 [--deny-robots]``.
"""

import html
import io
import json
import threading
import zipfile
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

FORM = "ctl0$CONTENU_PAGE$EntrepriseFormulaireDemande$"
FORM_ID = "ctl0_CONTENU_PAGE_EntrepriseFormulaireDemande_"
DEADLINE = "30/11/2026 12:00"


def _pdf(lines: list[str]) -> bytes:
    from tests.documents_helpers import make_pdf

    return make_pdf([lines])


def dce_zip() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("RC.pdf", _pdf(["REGLEMENT DE LA CONSULTATION", "Date limite : 30/11/2026"]))
        zf.writestr("CCTP.pdf", _pdf(["CAHIER DES CLAUSES TECHNIQUES", "Nettoyage des locaux"]))
    return out.getvalue()


@dataclass
class State:
    deny_robots: bool = False
    received: dict[str, Any] = field(default_factory=dict)
    hits: list[str] = field(default_factory=list)


def _page(title: str, body: str) -> bytes:
    return (
        f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>{title}</title>"
        f"</head><body>{body}</body></html>"
    ).encode()


def _consultation(number: str, code: str) -> bytes:
    if number == "1002":
        return _page("", "<p>L'accès à cette consultation n'est pas autorisé</p>")
    size = "738 Mo" if number == "1004" else "0,01 Mo"
    link = (
        "/index.php?page=Entreprise.EntrepriseDemandeTelechargementDce"
        f"&amp;id={number}&amp;orgAcronyme={code}"
    )
    return _page(
        "Détail d'une consultation",
        f"<h1>Détail de la consultation</h1><p>Date et heure limite de remise des plis :</p>"
        f"<p>{DEADLINE}</p><p>Référence : TEST-{number}</p>"
        f"<h2>Téléchargement</h2><a href='{link}'>Dossier de consultation - {size}</a>",
    )


def _form(number: str, error: str = "") -> bytes:
    if number == "1005":
        return _page("Maintenance", "<p>Le service est en maintenance.</p>")
    captcha = "<div class='h-captcha' data-sitekey='x'></div>" if number == "1003" else ""
    fields = "".join(
        f"<label>{label} <input type='text' name='{FORM}{name}' id='{FORM_ID}{name}'"
        f"{' maxlength=' + chr(39) + str(size) + chr(39) if size else ''}></label>"
        for label, name, size in (
            ("Nom", "nom", 0),
            ("Prénom", "prenom", 0),
            ("E-mail", "email", 0),
            ("Raison sociale", "raisonSocial", 0),
            ("SIREN", "siren", 9),
            ("Code établissement", "siret", 5),
        )
    )
    err = f"<span class='message-erreur' role='alert'>{html.escape(error)}</span>" if error else ""
    return _page(
        "PLACE - Plate-forme des achats de l'Etat",
        f"<h1>Téléchargement du Dossier de Consultation des Entreprises</h1>{err}{captcha}"
        f"<form method='post'>"
        f"<input type='radio' name='{FORM}RadioGroup' id='{FORM_ID}choixTelechargement'"
        f" value='choixTelechargement'><label for='{FORM_ID}choixTelechargement'>Je m'identifie"
        f"</label>{fields}"
        f"<input type='radio' name='{FORM}etablissementEntreprise' value='france'"
        f" id='{FORM_ID}france'><label for='{FORM_ID}france'>Établie en France</label>"
        f"<input type='radio' name='{FORM}etablissementEntreprise' value='etranger'"
        f" id='{FORM_ID}etranger'><label for='{FORM_ID}etranger'>Établie à l'étranger</label>"
        f"<input type='radio' name='{FORM}RadioGroup' id='{FORM_ID}choixAnonyme'"
        f" value='choixAnonyme'><label for='{FORM_ID}choixAnonyme'>Je souhaite télécharger"
        f" anonymement le Dossier de Consultation des Entreprises</label>"
        f"<input type='checkbox' name='{FORM}accepterConditions' id='{FORM_ID}accepterConditions'>"
        f"<label for='{FORM_ID}accepterConditions'>Je reconnais avoir pris connaissance des"
        f" conditions générales d'utilisation</label>"
        f"<input type='submit' name='ctl0$CONTENU_PAGE$validateButton' value='Valider'>"
        f"</form>",
    )


def _complete(number: str) -> bytes:
    return _page(
        "PLACE - Plate-forme des achats de l'Etat",
        "<h2>Téléchargement complet</h2><p>Cliquez sur le bouton suivant pour télécharger le"
        " Dossier de consultation dans son intégralité: DCE.zip - 0,01 Mo</p>"
        "<a href='javascript:;' onclick=\"document.getElementById('dl').submit()\">"
        "Télécharger le Dossier de consultation</a>"
        f"<form id='dl' method='post' action='/download?id={number}'></form>",
    )


def handler_for(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # quiet
            return

        def _send(
            self, body: bytes, kind: str = "text/html; charset=utf-8", **headers: str
        ) -> None:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            for key, value in headers.items():
                self.send_header(key.replace("_", "-"), value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            state.hits.append(self.path)
            parts = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
            if parts.path == "/robots.txt":
                rule = "/" if state.deny_robots else ""
                self._send(f"User-agent: *\nDisallow: {rule}\n".encode(), "text/plain")
            elif parts.path == "/_received":
                self._send(json.dumps(state.received).encode(), "application/json")
            elif parts.path.startswith("/entreprise/consultation/"):
                number = parts.path.rsplit("/", 1)[-1]
                self._send(_consultation(number, query.get("orgAcronyme", "")))
            elif parts.path == "/index.php" and query.get("page", "").endswith(
                "EntrepriseDemandeTelechargementDce"
            ):
                self._send(_form(query.get("id", "")))
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            state.hits.append(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            data = {
                k.removeprefix(FORM): v[0]
                for k, v in parse_qs(
                    self.rfile.read(length).decode(), keep_blank_values=True
                ).items()
            }
            parts = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            number = query.get("id", "")
            if parts.path == "/download":
                self._send(
                    dce_zip(),
                    "application/zip",
                    Content_Disposition='attachment; filename="DCE.zip"',
                )
                return
            state.received = {**data, "user_agent": self.headers.get("User-Agent", "")}
            if data.get("accepterConditions") != "on":
                self._send(_form(number, "Vous devez accepter les conditions d'utilisation."))
            elif number == "1006" and data.get("RadioGroup") == "choixTelechargement":
                self._send(_form(number, "Le SIRET saisi est invalide."))
            else:
                self._send(_complete(number))

    return Handler


def serve(port: int = 0, deny_robots: bool = False) -> tuple[ThreadingHTTPServer, State]:
    """Start the fake platform in a thread; ``port=0`` picks a free port."""
    state = State(deny_robots=deny_robots)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state
