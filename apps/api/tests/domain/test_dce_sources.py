from datetime import UTC, datetime

import pytest

from app.domain.dce_sources import (
    PageFacts,
    consultation_url,
    download_url,
    format_size,
    guide,
    parse_deadline,
    parse_size,
    recognize,
    terms_url,
    watch_change,
    watch_state,
)

PLACE = "https://www.marches-publics.gouv.fr"


@pytest.mark.parametrize(
    ("url", "site", "cid", "code"),
    [
        (f"{PLACE}/entreprise/consultation/3091292?orgAcronyme=h8j", "PLACE", "3091292", "h8j"),
        (
            f"{PLACE}/app.php/entreprise/consultation/3094882?orgAcronyme=f5j",
            "PLACE",
            "3094882",
            "f5j",
        ),
        (
            f"{PLACE}/?page=Entreprise.EntrepriseDetailConsultation&id=3094882&orgAcronyme=f5j",
            "PLACE",
            "3094882",
            "f5j",
        ),
        (
            f"{PLACE}/?page=Entreprise.EntrepriseAdvancedSearch&AllCons&id=3064274&orgAcronyme=f2h",
            "PLACE",
            "3064274",
            "f2h",
        ),
        (
            "https://marches.maximilien.fr/entreprise/consultation/948922?orgAcronyme=p1v",
            "Maximilien",
            "948922",
            "p1v",
        ),
        (
            "https://marches.megalis.bretagne.bzh/entreprise/consultation/241683?orgAcronyme=f9x",
            "Mégalis Bretagne",
            "241683",
            "f9x",
        ),
        (
            "https://marches.ternum-bfc.fr/entreprise/consultation/695276?orgAcronyme=e9m",
            "Territoires numériques BFC",
            "695276",
            "e9m",
        ),
        (
            "https://demat-ampa.fr/entreprise/consultation/611232?orgAcronyme=PP295",
            "AMPA",
            "611232",
            "PP295",
        ),
        (
            "https://marchespublics.exemple-region.fr/entreprise/consultation/42?orgAcronyme=z9z",
            "marchespublics.exemple-region.fr",
            "42",
            "z9z",
        ),
    ],
)
def test_atexo_links_seen_in_notices(url: str, site: str, cid: str, code: str) -> None:
    src = recognize(url)
    assert src is not None
    assert src.platform == "atexo"
    assert src.site == site
    assert (src.consultation_id, src.org_acronym) == (cid, code)
    assert src.automatic and not src.home_only


@pytest.mark.parametrize(
    "url", [f"{PLACE}/?page=Entreprise.AccueilEntreprise", "https://marches.maximilien.fr"]
)
def test_atexo_home_is_not_automatic(url: str) -> None:
    src = recognize(url)
    assert src is not None
    assert src.platform == "atexo"
    assert not src.automatic
    assert src.home_only


def test_other_platforms() -> None:
    aws = recognize(
        "https://www.marches-publics.info/mpiaws/index.cfm?fuseaction=dematEnt.login"
        "&amp;type=DCE&amp;IDM=1878216"
    )
    assert aws is not None and aws.platform == "aws"
    assert "&amp;" not in aws.url and "IDM=1878216" in aws.url
    assert not aws.automatic and not aws.home_only
    gm = recognize("https://gm.aws-achat.info//avis/index.cfm?fuseaction=dematEnt.login&IDM=7195")
    assert gm is not None and gm.platform == "aws"
    for url in (
        "https://www.achatpublic.com/sdm/ent/gen/ent_detail.do?PCSLID=CSL_2026_EgiMsoXRrb",
        "https://www.achatpublic.com/sdm/ent2/gen/ficheCsl.action?PCSLID=CSL_2026_l0LUrAK4iD",
    ):
        ap = recognize(url)
        assert ap is not None and ap.platform == "achatpublic"
    emp = recognize(
        "https://brl.e-marchespublics.com/pack/annonce_marche_public_34156_1186318.html"
    )
    assert emp is not None and emp.platform == "e_marchespublics"
    ms = recognize("https://www.marches-securises.fr")
    assert ms is not None and ms.platform == "marches_securises" and ms.home_only
    other = recognize("https://exemple.fr/dce")
    assert other is not None and other.platform == "other" and other.site == "exemple.fr"
    assert not other.home_only


def test_dirty_links() -> None:
    src = recognize(f"  {PLACE}/entreprise/consultation/3091292?orgAcronyme=H8J#pub  ")
    assert src is not None
    assert (src.consultation_id, src.org_acronym) == ("3091292", "H8J")
    assert src.url == f"{PLACE}/entreprise/consultation/3091292?orgAcronyme=H8J"
    assert src.automatic
    for bad in (None, "", "   ", "ftp://x/entreprise/consultation/1?orgAcronyme=a", "pas un lien"):
        assert recognize(bad) is None


def test_host_keeps_its_port_and_site_drops_it() -> None:
    src = recognize("http://127.0.0.1:8765/entreprise/consultation/1001?orgAcronyme=t1x")
    assert src is not None and src.automatic
    assert (src.scheme, src.host, src.site) == ("http", "127.0.0.1:8765", "127.0.0.1")


def test_urls_built_for_the_robot() -> None:
    src = recognize(
        f"{PLACE}/?page=Entreprise.EntrepriseDetailConsultation&id=3094882&orgAcronyme=f5j"
    )
    assert src is not None
    assert consultation_url(src) == f"{PLACE}/entreprise/consultation/3094882?orgAcronyme=f5j"
    assert download_url(src) == (
        f"{PLACE}/index.php?page=Entreprise.EntrepriseDemandeTelechargementDce"
        "&id=3094882&orgAcronyme=f5j"
    )
    # ledger ruling (pre-flight): the dialog links to the platform's terms
    assert terms_url(src) == f"{PLACE}/entreprise/footer/conditions-utilisation"
    aws = recognize("https://www.marches-publics.info/x")
    assert aws is not None and terms_url(aws) is None


def test_sizes() -> None:
    assert parse_size("10,56 Mo") == round(10.56 * 1048576)
    assert parse_size("738 Mo") == 738 * 1048576
    assert parse_size("136,42 Ko") == round(136.42 * 1024)
    assert parse_size("1,2 Go") == round(1.2 * 1024**3)
    assert parse_size("11.5 Mo") == round(11.5 * 1048576)
    assert parse_size("Mo") is None
    assert parse_size(None) is None
    assert format_size(250 * 1048576) == "250 Mo"
    assert format_size(738 * 1048576) == "738 Mo"
    assert format_size(round(1.2 * 1024**3)) == "1,2 Go"


def test_deadline() -> None:
    assert parse_deadline("30/11/2026 12:00") == datetime(2026, 11, 30, 11, 0, tzinfo=UTC)
    assert parse_deadline("Date limite : 18/06/2027 12:00 (heure de Paris)") == datetime(
        2027, 6, 18, 10, 0, tzinfo=UTC
    )
    assert parse_deadline("bientôt") is None
    assert parse_deadline(None) is None


def test_guides() -> None:
    assert guide("aws", None) == (
        "1. Cliquez sur « retirer le DCE en mode anonyme ».",
        "2. Tapez le code affiché, puis « Retrait anonyme ».",
        "3. Enregistrez le ZIP et glissez-le ci-dessous.",
    )
    assert guide("other", "26/BAT2102/02")[0] == (
        "1. Trouvez la consultation (référence : 26/BAT2102/02)."
    )
    assert guide("marches_securises", None)[0] == "1. Trouvez la consultation."
    assert len(guide("achatpublic", None)) == 3
    assert len(guide("e_marchespublics", None)) == 3


def test_watch_change() -> None:
    deadline = datetime(2026, 11, 30, 11, 0, tzinfo=UTC)
    now = datetime(2026, 11, 14, 5, 40, tzinfo=UTC)
    previous = watch_state(PageFacts("10,56 Mo", deadline, False), now)
    assert previous == {
        "size_label": "10,56 Mo",
        "deadline_at": "2026-11-30T11:00:00+00:00",
        "checked_at": "2026-11-14T05:40:00+00:00",
        "failures": 0,
        "stopped": False,
    }
    same = watch_change(previous, PageFacts("10,56 Mo", deadline, False))
    assert not same.size_changed and not same.deadline_changed
    size = watch_change(previous, PageFacts("10,60 Mo", deadline, False))
    assert size.size_changed and not size.deadline_changed
    later = datetime(2026, 12, 5, 11, 0, tzinfo=UTC)
    moved = watch_change(previous, PageFacts("10,56 Mo", later, False))
    assert moved.deadline_changed and moved.new_deadline == later
    blank = watch_change(previous, PageFacts(None, None, False))
    assert not blank.size_changed and not blank.deadline_changed
    first = watch_change(None, PageFacts("10,56 Mo", deadline, False))
    assert not first.size_changed and not first.deadline_changed
