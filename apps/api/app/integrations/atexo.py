"""The DCE robot for PLACE and the Atexo platforms (spec « Récupération des DCE », § 2, § 5, § 7.2).

A headless Chromium does what a person does: the consultation page (closed? size? deadline?),
the download request form (anonymous or on the company's behalf), the platform's terms, « Valider »,
then « Télécharger le Dossier de consultation ». It never solves a captcha, reads robots.txt,
introduces itself as Pilao, waits between pages and only reaches public addresses.
"""

import logging
import re
import time
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Request, Response, Route
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.core.config import get_settings
from app.domain.dce_sources import (
    DceSource,
    PageFacts,
    consultation_url,
    download_url,
    format_size,
    parse_deadline,
    parse_size,
)
from app.integrations.robot_net import addresses_of, url_allowed

logger = logging.getLogger("pilao.dce_robot")

ROBOT_NAME = "Pilao"
USER_AGENT_SUFFIX = "Pilao/1.0 (+https://app.pilao.pro/mentions-legales#robot)"
PAGE_GAP_SECONDS = 10.0
PAGE_TIMEOUT_SECONDS = 45
SETTLE_SECONDS = 15
DOWNLOAD_TIMEOUT_SECONDS = 300
CAPTCHA_MARKERS = ("captcha", "recaptcha", "hcaptcha", "turnstile")
MESSAGES = {
    "closed": "La plateforme refuse l'accès à cette consultation (close ou réservée).",
    "unreadable": "Pilao n'a pas su lire cette page. Ouvrez-la et déposez le ZIP.",
    "captcha": "Cette plateforme demande une vérification humaine.",
    "robots": "Cette plateforme n'accepte pas les robots.",
    "unavailable": "La plateforme ne répond pas. Réessayez plus tard.",
}
REFUSED = "La plateforme a refusé les informations de l'entreprise : {}"
TOO_BIG = (
    "Ce DCE fait {}, au-delà de la limite de {} : téléchargez-le vous-même et déposez les "
    "pièces utiles (RC, CCTP, CCAP…)."
)
_CLOSED = "acces a cette consultation n'est pas autorise"
_SIZE_LINK = re.compile(
    r"Dossier de consultation\s*-\s*(\d+(?:[.,]\d+)?)\s*([KMG]o)", re.IGNORECASE
)
_DEADLINE_TEXT = re.compile(
    r"limite de remise des plis\s*:?\s*(\d{2}/\d{2}/\d{4}\s+\d{1,2}[:h]\d{2})", re.IGNORECASE
)
_READY = re.compile(r"dossier de consultation|remise des plis|" + _CLOSED, re.IGNORECASE)
_SKIPPED_RESOURCES = {"image", "media", "font"}  # lighter on the platform's servers
_ERRORS = "[role=alert], .message-erreur, .erreur, .error, .alert-danger"


@dataclass(frozen=True)
class Identity:
    """What the company gives the buyer's platform when the DCE is retrieved on its behalf."""

    first_name: str
    last_name: str
    email: str
    company_name: str
    siren: str
    siret: str


@dataclass(frozen=True)
class Fetched:
    path: Path
    filename: str
    size_label: str | None
    deadline_at: datetime | None


class RobotError(Exception):
    """An expected refusal (closed, captcha, too big…): its message is shown in the dossier."""

    def __init__(self, outcome: str, message: str | None = None) -> None:
        self.outcome = outcome
        self.message = message or MESSAGES[outcome]
        super().__init__(self.message)


class RobotUnavailable(Exception):
    """The platform does not answer (down, too slow): worth another try later."""


class DceRobot(Protocol):
    def inspect(self, src: DceSource) -> PageFacts: ...

    def fetch(
        self, src: DceSource, identity: Identity | None, dest: Path, max_bytes: int
    ) -> Fetched: ...


def _plain(text: str) -> str:
    """Lower case, no accents, straight apostrophes."""
    decomposed = unicodedata.normalize("NFKD", text.replace("’", "'"))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _safe_name(name: str | None) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return base or "DCE.zip"


class AtexoRobot:
    def __init__(
        self,
        *,
        browser_path: str = "",
        allow_private: bool = False,
        page_gap: float = PAGE_GAP_SECONDS,
        robots_ttl: float = 86400.0,
    ) -> None:
        self._browser_path = browser_path
        self._allow_private = allow_private
        self._gap = page_gap
        self._robots_ttl = robots_ttl
        self._robots: dict[str, tuple[float, RobotFileParser | None]] = {}
        self._hosts: dict[str, bool] = {}
        self._last_load = 0.0

    # ---------- the two things it does ----------------------------------------------------

    def inspect(self, src: DceSource) -> PageFacts:
        url = consultation_url(src)
        self._precheck(src, url)
        with self._errors(), self._page() as page:
            self._check_robots(page, src, url)
            self._goto(page, url)
            return self._facts(page)

    def fetch(
        self, src: DceSource, identity: Identity | None, dest: Path, max_bytes: int
    ) -> Fetched:
        url = consultation_url(src)
        self._precheck(src, url)
        with self._errors(), self._page() as page:
            self._check_robots(page, src, url)
            self._goto(page, url)
            facts = self._facts(page)
            if facts.closed:
                raise RobotError("closed")
            announced = parse_size(facts.size_label)
            if announced is not None and facts.size_label and announced > max_bytes:
                raise RobotError(
                    "too_big", TOO_BIG.format(facts.size_label, format_size(max_bytes))
                )
            self._goto(page, download_url(src))
            if any(marker in page.content().lower() for marker in CAPTCHA_MARKERS):
                raise RobotError("captcha")
            self._fill_form(page, identity)
            self._pause()
            page.locator(
                "input[type=submit][name$='validateButton'], input[type=submit][value='Valider']"
            ).first.click()
            self._settle(page)
            self._check_page(page)
            link = page.get_by_text("Télécharger le Dossier de consultation", exact=True)
            if link.count() == 0:
                error = self._error_text(page)
                if identity is not None and error:
                    raise RobotError("refused_identity", REFUSED.format(error))
                raise RobotError("unreadable")
            self._pause()
            with page.expect_download(timeout=DOWNLOAD_TIMEOUT_SECONDS * 1000) as info:
                link.first.click()
            download = info.value
            if not self._allowed(download.url):  # a redirect led it elsewhere
                download.cancel()
                raise RobotError("unreadable")
            filename = _safe_name(download.suggested_filename)
            path = dest / filename
            download.save_as(path)
        size = path.stat().st_size
        if size > max_bytes:
            path.unlink(missing_ok=True)
            raise RobotError("too_big", TOO_BIG.format(format_size(size), format_size(max_bytes)))
        return Fetched(path, filename, facts.size_label, facts.deadline_at)

    # ---------- addresses, robots.txt, pace --------------------------------------------------

    def _precheck(self, src: DceSource, url: str) -> None:
        """Only the known Atexo platforms (``ATEXO_SITES``), never a host a user chose: a page
        there could send the browser into the server's network (final review C1)."""
        if not self._allow_private and not src.known:
            raise RobotError("unreadable")
        if url_allowed(url, self._allow_private):
            return
        host = urlsplit(url).hostname or ""
        if url_allowed(url, self._allow_private, resolve=False) and addresses_of(host) is None:
            raise RobotUnavailable(f"{host} does not resolve")
        raise RobotError("unreadable")

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key not in self._hosts:
            self._hosts[key] = url_allowed(url, self._allow_private)
        return self._hosts[key]

    def _check_page(self, page: Page) -> None:
        if not self._allowed(page.url):
            raise RobotError("unreadable")

    def _check_chain(self, response: Response) -> None:
        """Playwright routes only the first request of a redirect chain: every hop is checked
        afterwards, and a refused one stops the robot before it reads anything."""
        request: Request | None = response.request
        while request is not None:
            if not self._allowed(request.url):
                raise RobotError("unreadable")
            request = request.redirected_from

    def _filter(self, route: Route) -> None:
        request = route.request
        if request.resource_type in _SKIPPED_RESOURCES or not self._allowed(request.url):
            route.abort("blockedbyclient")
        else:
            route.continue_()

    def _check_robots(self, page: Page, src: DceSource, url: str) -> None:
        base = f"{src.scheme}://{src.host}"
        cached = self._robots.get(base)
        if cached is None or time.monotonic() - cached[0] > self._robots_ttl:
            self._pause()
            response = page.context.request.get(
                f"{base}/robots.txt", timeout=15_000, max_redirects=0  # never followed elsewhere
            )
            if response.status >= 500:
                raise RobotUnavailable(f"robots.txt answered {response.status}")
            parser: RobotFileParser | None = None
            if response.ok:
                parser = RobotFileParser()
                parser.parse(response.text().splitlines())
            cached = (time.monotonic(), parser)
            self._robots[base] = cached
        if cached[1] is not None and not cached[1].can_fetch(ROBOT_NAME, url):
            raise RobotError("robots")

    def _pause(self) -> None:
        wait = self._gap - (time.monotonic() - self._last_load)
        if wait > 0:
            time.sleep(wait)
        self._last_load = time.monotonic()

    # ---------- the browser -------------------------------------------------------------------

    @contextmanager
    def _page(self) -> Iterator[Page]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=self._browser_path or None)
            try:
                agent = (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    f"Chrome/{browser.version} Safari/537.36 {USER_AGENT_SUFFIX}"
                )
                context = browser.new_context(
                    locale="fr-FR",
                    accept_downloads=True,
                    user_agent=agent,
                    service_workers="block",  # they would bypass the address filter
                )
                context.route("**/*", self._filter)
                page = context.new_page()
                page.set_default_timeout(PAGE_TIMEOUT_SECONDS * 1000)
                yield page
            finally:
                browser.close()

    @contextmanager
    def _errors(self) -> Iterator[None]:
        try:
            yield
        except (RobotError, RobotUnavailable):
            raise
        except PlaywrightTimeoutError as exc:
            raise RobotUnavailable(str(exc)) from exc
        except PlaywrightError as exc:
            if "net::" in str(exc):
                raise RobotUnavailable(str(exc)) from exc
            logger.warning("DCE robot could not read a page: %s", str(exc)[:300])
            raise RobotError("unreadable") from exc

    def _goto(self, page: Page, url: str) -> None:
        self._pause()
        response = page.goto(url, wait_until="domcontentloaded")
        if response is not None:
            self._check_chain(response)
        if response is not None and response.status >= 500:
            raise RobotUnavailable(f"{url} answered {response.status}")
        if response is not None and response.status >= 400:
            raise RobotError("unreadable")
        self._settle(page)

    def _settle(self, page: Page) -> None:
        """Pages built by script take a moment: wait for the network, then for the text."""
        try:
            page.wait_for_load_state("networkidle", timeout=SETTLE_SECONDS * 1000)
        except PlaywrightTimeoutError:
            pass
        deadline = time.monotonic() + SETTLE_SECONDS
        while time.monotonic() < deadline:
            if _READY.search(_plain(page.inner_text("body"))):
                return
            page.wait_for_timeout(500)

    # ---------- reading and filling ---------------------------------------------------------

    @staticmethod
    def _facts(page: Page) -> PageFacts:
        text = page.inner_text("body")
        size = _SIZE_LINK.search(text)
        deadline = _DEADLINE_TEXT.search(text)
        return PageFacts(
            size_label=f"{size.group(1)} {size.group(2)}" if size else None,
            deadline_at=parse_deadline(deadline.group(1)) if deadline else None,
            closed=_CLOSED in _plain(text),
        )

    def _fill_form(self, page: Page, identity: Identity | None) -> None:
        choice = "choixTelechargement" if identity is not None else "choixAnonyme"
        radio = page.locator(f"input[type=radio][id$='{choice}']")
        terms = page.locator("input[type=checkbox][id$='accepterConditions']")
        if radio.count() == 0 or terms.count() == 0:
            raise RobotError("unreadable")
        radio.first.check()
        if identity is not None:
            values = {
                "prenom": identity.first_name,
                "nom": identity.last_name,
                "email": identity.email,
                "raisonSocial": identity.company_name,
                "siren": identity.siren,
            }
            for suffix, value in values.items():
                field = page.locator(f"input[name$='${suffix}']")
                if field.count():
                    field.first.fill(value)
            siret = page.locator("input[name$='$siret']")
            if siret.count():
                # Atexo asks for the 5-digit establishment code after the SIREN (spec § 11)
                short = siret.first.get_attribute("maxlength") == "5"
                siret.first.fill(identity.siret[-5:] if short else identity.siret)
            established = page.locator("input[type=radio][name$='etablissementEntreprise']")
            if established.count():
                established.first.check()
        terms.first.check()

    @staticmethod
    def _error_text(page: Page) -> str:
        for element in page.locator(_ERRORS).all():
            text = " ".join(element.inner_text().split())
            if text:
                return text[:200]
        return ""


def get_robot() -> DceRobot:
    settings = get_settings()
    return AtexoRobot(
        browser_path=settings.dce_robot_browser_path,
        allow_private=settings.dce_robot_allow_private_hosts,
    )
