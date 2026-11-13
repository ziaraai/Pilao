"""The Atexo robot in a real headless browser, against the fake platform (no Internet)."""

import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.dce_sources import DceSource, PageFacts, recognize
from app.integrations.atexo import USER_AGENT_SUFFIX, AtexoRobot, Identity, RobotError
from tests.fixtures.fake_atexo import State, serve

MAX = 250 * 1024 * 1024
IDENTITY = Identity(
    first_name="Sabrina",
    last_name="Martin",
    email="sabrina@exemple.fr",
    company_name="Propreté Démo",
    siren="123456789",
    siret="12345678900017",
)


def _browser_works() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _browser_works(), reason="Chromium for Playwright is not installed here"
)


@pytest.fixture(scope="module")
def platform() -> Iterator[tuple[str, State]]:
    server, state = serve()
    yield f"http://127.0.0.1:{server.server_address[1]}", state
    server.shutdown()


@pytest.fixture
def robot() -> AtexoRobot:
    return AtexoRobot(allow_private=True, page_gap=0)


def _src(base: str, number: int) -> DceSource:
    src = recognize(f"{base}/entreprise/consultation/{number}?orgAcronyme=t1x")
    assert src is not None and src.automatic
    return src


def _outcome(
    robot: AtexoRobot, src: DceSource, tmp_path: Path, identity: Identity | None = None
) -> RobotError:
    with pytest.raises(RobotError) as caught:
        robot.fetch(src, identity, tmp_path, MAX)
    return caught.value


def test_anonymous_fetch(platform: tuple[str, State], robot: AtexoRobot, tmp_path: Path) -> None:
    base, state = platform
    fetched = robot.fetch(_src(base, 1001), None, tmp_path, MAX)
    with zipfile.ZipFile(fetched.path) as zf:
        assert sorted(zf.namelist()) == ["CCTP.pdf", "RC.pdf"]
    assert fetched.filename == "DCE.zip"
    assert fetched.size_label == "0,01 Mo"
    assert fetched.deadline_at == datetime(2026, 11, 30, 11, 0, tzinfo=UTC)
    assert state.received["RadioGroup"] == "choixAnonyme"
    assert state.received["accepterConditions"] == "on"
    assert "nom" not in state.received or state.received["nom"] == ""
    assert state.received["user_agent"].endswith(USER_AGENT_SUFFIX)


def test_identified_fetch_sends_the_company(
    platform: tuple[str, State], robot: AtexoRobot, tmp_path: Path
) -> None:
    base, state = platform
    robot.fetch(_src(base, 1001), IDENTITY, tmp_path, MAX)
    got = state.received
    assert got["RadioGroup"] == "choixTelechargement"
    assert (got["prenom"], got["nom"], got["email"]) == ("Sabrina", "Martin", "sabrina@exemple.fr")
    assert got["raisonSocial"] == "Propreté Démo"
    assert got["siren"] == "123456789"
    assert got["siret"] == "00017"  # the field takes the 5-digit establishment code
    assert got["etablissementEntreprise"] == "france"


def test_closed(platform: tuple[str, State], robot: AtexoRobot, tmp_path: Path) -> None:
    error = _outcome(robot, _src(platform[0], 1002), tmp_path)
    assert error.outcome == "closed"
    assert error.message == (
        "La plateforme refuse l'accès à cette consultation (close ou réservée)."
    )


def test_captcha(platform: tuple[str, State], robot: AtexoRobot, tmp_path: Path) -> None:
    error = _outcome(robot, _src(platform[0], 1003), tmp_path)
    assert error.outcome == "captcha"
    assert error.message == "Cette plateforme demande une vérification humaine."


def test_too_big(platform: tuple[str, State], robot: AtexoRobot, tmp_path: Path) -> None:
    error = _outcome(robot, _src(platform[0], 1004), tmp_path)
    assert error.outcome == "too_big"
    assert error.message == (
        "Ce DCE fait 738 Mo, au-delà de la limite de 250 Mo : téléchargez-le vous-même et "
        "déposez les pièces utiles (RC, CCTP, CCAP…)."
    )
    assert list(tmp_path.iterdir()) == []


def test_unreadable(platform: tuple[str, State], robot: AtexoRobot, tmp_path: Path) -> None:
    error = _outcome(robot, _src(platform[0], 1005), tmp_path)
    assert error.outcome == "unreadable"
    assert error.message == "Pilao n'a pas su lire cette page. Ouvrez-la et déposez le ZIP."


def test_identity_refused(platform: tuple[str, State], robot: AtexoRobot, tmp_path: Path) -> None:
    error = _outcome(robot, _src(platform[0], 1006), tmp_path, IDENTITY)
    assert error.outcome == "refused_identity"
    assert error.message == (
        "La plateforme a refusé les informations de l'entreprise : Le SIRET saisi est invalide."
    )


def test_robots_txt_forbids(robot: AtexoRobot, tmp_path: Path) -> None:
    server, state = serve(deny_robots=True)
    try:
        error = _outcome(
            robot, _src(f"http://127.0.0.1:{server.server_address[1]}", 1001), tmp_path
        )
    finally:
        server.shutdown()
    assert error.outcome == "robots"
    assert error.message == "Cette plateforme n'accepte pas les robots."
    assert state.hits == ["/robots.txt"]


def test_private_address_refused(platform: tuple[str, State], tmp_path: Path) -> None:
    base, state = platform
    before = len(state.hits)
    strict = AtexoRobot(allow_private=False, page_gap=0)
    error = _outcome(strict, _src(base, 1001), tmp_path)
    assert error.outcome == "unreadable"
    assert len(state.hits) == before  # refused before any request


def test_inspect(platform: tuple[str, State], robot: AtexoRobot) -> None:
    base, _ = platform
    deadline = datetime(2026, 11, 30, 11, 0, tzinfo=UTC)
    assert robot.inspect(_src(base, 1001)) == PageFacts("0,01 Mo", deadline, False)
    assert robot.inspect(_src(base, 1002)).closed
