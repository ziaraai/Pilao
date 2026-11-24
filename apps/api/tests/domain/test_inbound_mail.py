"""The DCE e-mail address (24/11): reading an e-mail sent or forwarded to dce+CODE@pilao.pro."""

import uuid
from email.message import EmailMessage

from app.domain.inbound_mail import (
    DossierRef,
    code_from,
    is_update_notice,
    match_dossier,
    new_code,
    parse,
)

PDF = b"%PDF-1.4 RC"


def mail(**kw: object) -> EmailMessage:
    m = EmailMessage()
    m["From"] = kw.get("sender", "Faycal <faycal@engpro.fr>")
    m["To"] = kw.get("to", "dce+k7x2m9@pilao.pro")
    m["Subject"] = kw.get("subject", "TR: DCE 26SERV02 Nettoyage des collèges")
    m["Message-ID"] = kw.get("message_id", "<abc@engpro.fr>")
    m.set_content(str(kw.get("text", "Bonjour, voici le DCE.")))
    return m


def test_reads_sender_subject_text_and_attachments() -> None:
    m = mail()
    m.add_attachment(PDF, maintype="application", subtype="pdf", filename="RC.pdf")
    m.add_attachment(b"PK zip", maintype="application", subtype="zip", filename="Pièces.zip")
    parsed = parse(m.as_bytes())
    assert parsed.sender == "faycal@engpro.fr"
    assert parsed.subject == "TR: DCE 26SERV02 Nettoyage des collèges"
    assert parsed.message_id == "<abc@engpro.fr>"
    assert "voici le DCE" in parsed.text
    assert [(a.filename, a.data) for a in parsed.attachments] == [
        ("RC.pdf", PDF),
        ("Pièces.zip", b"PK zip"),
    ]


def test_takes_the_attachments_of_an_email_forwarded_as_attachment() -> None:
    inner = mail(subject="Mise à disposition du DCE")
    inner.add_attachment(PDF, maintype="application", subtype="pdf", filename="CCTP.pdf")
    outer = mail(subject="TR: Mise à disposition du DCE")
    outer.add_attachment(inner)  # Outlook « Transférer en tant que pièce jointe »
    parsed = parse(outer.as_bytes())
    assert [a.filename for a in parsed.attachments] == ["CCTP.pdf"]
    assert "Mise à disposition du DCE" in parsed.text


def test_finds_the_links_of_the_email() -> None:
    m = mail(
        text="Le DCE a été modifié : https://www.marches-publics.gouv.fr/entreprise/consultation/1?orgAcronyme=a1b ."
    )
    links = parse(m.as_bytes()).links
    assert links == [
        "https://www.marches-publics.gouv.fr/entreprise/consultation/1?orgAcronyme=a1b"
    ]


def test_finds_the_company_code_in_the_address() -> None:
    assert code_from(["dce+k7x2m9@pilao.pro"]) == "k7x2m9"
    assert code_from(["Pilao <DCE+K7X2M9@Pilao.pro>", "autre@x.fr"]) == "k7x2m9"
    assert code_from(["dce@pilao.pro"]) is None
    assert code_from(["dce+k7x2m9@ailleurs.fr"]) is None  # another domain
    assert code_from(["dce+../../x@pilao.pro"]) is None  # only letters and digits
    # the address the server delivered to (forwarded, Bcc): the parsed recipients carry it
    m = mail(to="moi@engpro.fr")
    m["Delivered-To"] = "dce+k7x2m9@pilao.pro"
    assert code_from(parse(m.as_bytes()).recipients) == "k7x2m9"


def test_codes_are_short_and_unambiguous() -> None:
    codes = {new_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(len(c) == 6 and c.isalnum() and c == c.lower() for c in codes)
    assert not any(ch in c for c in codes for ch in "0o1il")  # read aloud, typed by hand


def test_spots_a_notice_that_the_dce_changed() -> None:
    assert is_update_notice("Avis de modification - consultation 26SERV02", "")
    assert is_update_notice("Votre consultation", "Un rectificatif a été publié.")
    assert is_update_notice("Nouvelle version du DCE disponible", "")
    assert is_update_notice("Mise à jour du dossier de consultation", "")
    assert not is_update_notice("TR: DCE 26SERV02", "Voici le DCE.")


def test_finds_the_dossier_by_its_reference_then_its_title() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    dossiers = [
        DossierRef(a, "26SERV02", "Nettoyage des collèges de la Loire", "Département de la Loire"),
        DossierRef(b, None, "Nettoyage des bureaux de la mairie de Montbrison", "Montbrison"),
        DossierRef(c, "AB", "Vitrerie", None),  # too short a reference to be trusted
    ]
    assert match_dossier("TR: DCE 26-SERV-02", "", dossiers) == a  # dashes or not
    assert match_dossier("TR: DCE 26SERV02", "", dossiers) == a
    assert match_dossier("Fwd: consultation", "Réf. : 26serv02", dossiers) == a
    assert (
        match_dossier("DCE - Nettoyage des bureaux de la mairie de Montbrison", "", dossiers) == b
    )
    assert match_dossier("DCE Vitrerie AB", "", dossiers) is None
    assert match_dossier("Bonjour", "Voici le DCE.", dossiers) is None
    # two dossiers with the same reference: Pilao does not guess
    twin = DossierRef(uuid.uuid4(), "26SERV02", "Lot 2", None)
    assert match_dossier("TR: DCE 26SERV02", "", [*dossiers, twin]) is None


def test_trusts_a_sender_only_when_the_server_checked_its_domain() -> None:
    from app.domain.inbound_mail import authenticated

    ok = "mail.pilao.pro; dmarc=pass (p=none) header.from=engpro.fr; spf=pass smtp.mailfrom=engpro.fr"
    m = mail()
    m["Authentication-Results"] = ok
    parsed = parse(m.as_bytes())
    assert parsed.auth_results == [ok]
    assert authenticated(parsed.sender, parsed.auth_results)
    # DKIM signed by the sender's domain
    assert authenticated("a@engpro.fr", ["mx; dkim=pass header.d=engpro.fr header.s=default"])
    # SPF of the sender's own domain
    assert authenticated("a@engpro.fr", ["mx; spf=pass smtp.mailfrom=bounce@engpro.fr"])
    # a pass for another domain, a failure, or no check at all: not trusted
    assert not authenticated("a@engpro.fr", ["mx; dkim=pass header.d=spam.example"])
    assert not authenticated("a@engpro.fr", ["mx; dmarc=fail header.from=engpro.fr"])
    assert not authenticated("a@engpro.fr", [])
    # only the topmost header counts: the one our server added (a lower one may be forged)
    forged = "mx; dmarc=pass header.from=engpro.fr"
    assert not authenticated("a@engpro.fr", ["mx; dmarc=fail header.from=engpro.fr", forged])
    # and only when it comes from our server, if its name is known
    assert not authenticated("a@engpro.fr", [forged], server="mail.pilao.pro")
    assert authenticated(
        "a@engpro.fr", [ok.replace("dmarc=pass (p=none) ", "")], server="mail.pilao.pro"
    )


def test_a_dossier_opened_from_an_email_takes_its_subject_as_title() -> None:
    from app.domain.inbound_mail import title_from_subject

    assert (
        title_from_subject("TR: Mise à disposition du DCE - Nettoyage de la piscine")
        == "Nettoyage de la piscine"
    )
    assert title_from_subject("Fwd: RE: DCE : Entretien des locaux") == "Entretien des locaux"
    assert title_from_subject("Nettoyage des vitres") == "Nettoyage des vitres"
    assert title_from_subject("TR: ") == "Dossier reçu par e-mail"
    assert len(title_from_subject("x" * 500)) == 200


def test_the_logo_of_a_signature_is_not_a_piece() -> None:
    m = mail()
    m.add_alternative("<p>Bonjour</p><img src='cid:logo1'>", subtype="html")
    html_part = m.get_payload()[-1]
    html_part.add_related(
        b"\x89PNG logo", maintype="image", subtype="png", cid="<logo1>", filename="image001.png"
    )
    m.add_attachment(PDF, maintype="application", subtype="pdf", filename="RC.pdf")
    assert [a.filename for a in parse(m.as_bytes()).attachments] == ["RC.pdf"]
