"""Where a notice's DCE lives, read from its link (spec « Récupération des DCE », § 3 and § 7.1).

Pure functions: no network. PLACE and the regional Atexo platforms are recognised by the shape
of their consultation links, so any Atexo site works, named or not; the robot only runs on an
Atexo link that carries both the consultation number and the buyer's code.
"""

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qs, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

Platform = Literal["atexo", "aws", "achatpublic", "e_marchespublics", "marches_securises", "other"]

PARIS = ZoneInfo("Europe/Paris")
ATEXO_SITES: dict[str, str] = {
    "www.marches-publics.gouv.fr": "PLACE",
    "marches-publics.gouv.fr": "PLACE",
    "marches.maximilien.fr": "Maximilien",
    "marches.megalis.bretagne.bzh": "Mégalis Bretagne",
    "marches.ternum-bfc.fr": "Territoires numériques BFC",
    "demat-ampa.fr": "AMPA",
    "plateforme.alsacemarchespublics.eu": "Alsace Marchés Publics",
    "www.mpe76.fr": "MPE 76",
}
# hostname suffix -> platform (captcha or no robots: guided retrieval only)
_OTHER_PLATFORMS: tuple[tuple[str, Platform], ...] = (
    ("marches-publics.info", "aws"),
    ("aws-achat.info", "aws"),
    ("achatpublic.com", "achatpublic"),
    ("e-marchespublics.com", "e_marchespublics"),
    ("marches-securises.fr", "marches_securises"),
)
_CONSULTATION_PATH = re.compile(r"^(?:/(?:app|index)\.php)?/entreprise/consultation/(\d+)/?$")
_DETAIL_PAGES = {
    "Entreprise.EntrepriseDetailConsultation",
    "Entreprise.EntrepriseDetailsConsultation",
    "Entreprise.EntrepriseDemandeTelechargementDce",
}
_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(Ko|Mo|Go)\b", re.IGNORECASE)
_FACTORS = {"ko": 1024, "mo": 1024**2, "go": 1024**3}
_DEADLINE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2})[:h](\d{2})")


@dataclass(frozen=True)
class DceSource:
    url: str  # the cleaned link
    platform: Platform
    site: str  # « PLACE », « Maximilien »… else the domain, without its port
    host: str  # domain with its port, to build addresses
    scheme: str
    consultation_id: str | None
    org_acronym: str | None

    @property
    def automatic(self) -> bool:
        return self.platform == "atexo" and bool(self.consultation_id and self.org_acronym)

    @property
    def home_only(self) -> bool:
        if self.platform == "atexo":
            return self.consultation_id is None
        parts = urlsplit(self.url)
        return parts.path in ("", "/") and not parts.query


@dataclass(frozen=True)
class PageFacts:
    """What the public page of an Atexo consultation shows."""

    size_label: str | None  # « 10,56 Mo »
    deadline_at: datetime | None
    closed: bool


@dataclass(frozen=True)
class Change:
    size_changed: bool
    deadline_changed: bool
    new_deadline: datetime | None


def _platform(hostname: str) -> Platform | None:
    for suffix, platform in _OTHER_PLATFORMS:
        if hostname == suffix or hostname.endswith("." + suffix):
            return platform
    return None


def _atexo_ids(path: str, query: dict[str, list[str]]) -> tuple[bool, str | None, str | None]:
    """(is an Atexo link, consultation number, buyer's code)."""
    code = next(iter(query.get("orgAcronyme") or []), None) or None
    match = _CONSULTATION_PATH.match(path)
    if match:
        return True, match.group(1), code
    page = (query.get("page") or [""])[0]
    if page in _DETAIL_PAGES or (
        page == "Entreprise.EntrepriseAdvancedSearch" and "AllCons" in query
    ):
        number = next(iter(query.get("id") or query.get("refConsultation") or []), None)
        return True, number if number and number.isdigit() else None, code
    if page.startswith("Entreprise."):
        return True, None, code
    return False, None, None


def recognize(url: str | None) -> DceSource | None:
    """The source behind a link, or ``None`` when it is not an http(s) link."""
    if not url or not url.strip():
        return None
    try:
        parts = urlsplit(html.unescape(url.strip()))
        hostname = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not hostname:
        return None
    scheme = parts.scheme.lower()
    host = f"{hostname}:{port}" if port else hostname
    clean = urlunsplit((scheme, host, parts.path, parts.query, ""))
    query = parse_qs(parts.query, keep_blank_values=True)
    is_atexo, number, code = _atexo_ids(parts.path, query)
    if is_atexo or hostname in ATEXO_SITES:
        return DceSource(
            clean, "atexo", ATEXO_SITES.get(hostname, hostname), host, scheme, number, code
        )
    return DceSource(clean, _platform(hostname) or "other", hostname, host, scheme, None, None)


def consultation_url(src: DceSource) -> str:
    return (
        f"{src.scheme}://{src.host}/entreprise/consultation/{src.consultation_id}"
        f"?orgAcronyme={src.org_acronym}"
    )


def download_url(src: DceSource) -> str:
    return (
        f"{src.scheme}://{src.host}/index.php?page=Entreprise.EntrepriseDemandeTelechargementDce"
        f"&id={src.consultation_id}&orgAcronyme={src.org_acronym}"
    )


def terms_url(src: DceSource) -> str | None:
    """The platform's terms of use, which Pilao accepts on the company's behalf (Atexo only)."""
    if src.platform != "atexo":
        return None
    return f"{src.scheme}://{src.host}/entreprise/footer/conditions-utilisation"


def parse_size(label: str | None) -> int | None:
    match = _SIZE.search(label or "")
    if match is None:
        return None
    return round(float(match.group(1).replace(",", ".")) * _FACTORS[match.group(2).lower()])


def format_size(n: int) -> str:
    mo = n / 1024**2
    if mo >= 1024:
        value, unit = mo / 1024, "Go"
    else:
        value, unit = mo, "Mo"
    text = f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"
    return f"{text.replace('.', ',')} {unit}"


def parse_deadline(text: str | None) -> datetime | None:
    """« 30/11/2026 12:00 » (Paris time) as UTC."""
    match = _DEADLINE.search(text or "")
    if match is None:
        return None
    day, month, year, hour, minute = (int(g) for g in match.groups())
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=PARIS)
    except ValueError:
        return None
    return local.astimezone(UTC)


_DROP = "3. Glissez le ZIP ci-dessous."


def guide(platform: Platform, reference: str | None) -> tuple[str, ...]:
    """The 3-line memo shown beside « Ouvrir la page du DCE » (spec § 4.1)."""
    if platform == "aws":
        return (
            "1. Cliquez sur « retirer le DCE en mode anonyme ».",
            "2. Tapez le code affiché, puis « Retrait anonyme ».",
            "3. Enregistrez le ZIP et glissez-le ci-dessous.",
        )
    if platform == "achatpublic":
        return (
            "1. Sur la fiche, ouvrez « Dossier de consultation ».",
            (
                "2. Connectez-vous ou choisissez le retrait sans compte, puis répondez à la "
                "vérification."
            ),
            _DROP,
        )
    if platform == "e_marchespublics":
        return (
            "1. Cliquez sur « Accédez au dossier de manière anonyme ».",
            "2. Recopiez le code de vérification.",
            _DROP,
        )
    if platform == "atexo":  # the robot is switched off
        return (
            "1. Cliquez sur « Dossier de consultation ».",
            (
                "2. Choisissez le téléchargement anonyme ou identifiez-vous, acceptez les "
                "conditions, puis « Valider » et « Télécharger le Dossier de consultation »."
            ),
            _DROP,
        )
    found = (
        f"1. Trouvez la consultation (référence : {reference})."
        if reference
        else ("1. Trouvez la consultation.")
    )
    return (found, "2. Téléchargez le dossier de consultation.", _DROP)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def watch_state(
    facts: PageFacts, now: datetime, failures: int = 0, stopped: bool = False
) -> dict[str, Any]:
    """The shape of ``bids.dce_watch``."""
    return {
        "size_label": facts.size_label,
        "deadline_at": _iso(facts.deadline_at),
        "checked_at": now.isoformat(),
        "failures": failures,
        "stopped": stopped,
    }


def watch_change(previous: dict[str, Any] | None, facts: PageFacts) -> Change:
    """A value missing on either side is never a change (no false alert)."""
    if not previous:
        return Change(False, False, None)
    old_size = previous.get("size_label")
    size_changed = bool(old_size and facts.size_label and old_size != facts.size_label)
    old_raw = previous.get("deadline_at")
    old_deadline = datetime.fromisoformat(old_raw) if old_raw else None
    deadline_changed = bool(
        old_deadline and facts.deadline_at and old_deadline != facts.deadline_at
    )
    return Change(size_changed, deadline_changed, facts.deadline_at if deadline_changed else None)
