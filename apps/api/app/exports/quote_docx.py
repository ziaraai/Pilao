"""The company's own quote for a consultation, as a Word file (ADR-052).

In the memoir's style (logo, brand colour, page numbers). Everything in it comes from the
profile, the dossier, the « Prix » tab or a cited CCTP page; a missing fact of the company is
written ``[À COMPLÉTER : …]``, never guessed.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.domain.quote import QuoteRow, QuoteTable, signature_line, vat_of
from app.exports.dc_forms import french_date
from app.exports.docx_builder import DocBuilder, todo

HEADERS = ("Désignation", "Unité", "Quantité", "Prix unitaire HT", "Total HT")
WIDTHS = (7.4, 1.8, 2.2, 2.6, 2.6)


def money(cents: int) -> str:
    """« 1 875,00 € »."""
    sign = "-" if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    return f"{sign}{euros:,}".replace(",", " ") + f",{rest:02d} €"


def quantity(value: Decimal | None) -> str:
    if value is None:
        return "—"
    plain = value.quantize(Decimal(1)) if value == value.to_integral() else value.normalize()
    return format(plain, ",f").replace(",", " ").replace(".", ",")


def vat_label(vat_bp: int) -> str:
    whole, rest = divmod(vat_bp, 100)
    return f"{whole} %" if rest == 0 else f"{whole},{rest:02d}".rstrip("0") + " %"


def _siret(siret: str) -> str:
    s = siret.replace(" ", "")
    return f"{s[:3]} {s[3:6]} {s[6:9]} {s[9:]}" if len(s) == 14 else s


@dataclass(frozen=True)
class Company:
    name: str
    legal_form: str | None
    siret: str
    address_line: str | None
    postal_code: str | None
    city: str | None
    phone: str | None
    email: str | None
    signatory_name: str | None  # « M. Exemple »
    signatory_role: str | None  # « gérant »


@dataclass(frozen=True)
class QuoteDocData:
    number: str
    issued: date
    validity_days: int
    vat_bp: int
    company: Company
    client: str | None
    contact: str | None  # « Mme Exemple — contact@… »
    subject: str
    reference: str | None
    inclusions: list[dict[str, Any]]
    table: QuoteTable
    brand_color: str | None
    logo: bytes | None


def _rows(rows: list[QuoteRow]) -> list[list[str]]:
    out: list[list[str]] = []
    section: str | None = None
    for r in rows:
        if r.section and r.section != section:
            out.append([f"**{r.section}**", "", "", "", ""])
        section = r.section
        out.append(
            [
                r.label or r.section,
                r.unit or "—",
                quantity(r.quantity),
                money(r.price_cents) if r.price_cents is not None else "—",
                money(r.total_cents) if r.total_cents is not None else "—",
            ]
        )
    return out


def build_quote(d: QuoteDocData) -> DocBuilder:
    c = d.company
    b = DocBuilder(brand_color=d.brand_color, logo=d.logo, company=c.name)
    b.header_footer(c.name, f"Devis n° {d.number}")
    until = d.issued + timedelta(days=d.validity_days)
    b.title(
        f"Devis n° {d.number}",
        f"Du {french_date(d.issued)}, valable {d.validity_days} jours, "
        f"jusqu'au {french_date(until)}",
    )

    b.heading("Entreprise", 2)
    b.paragraph(f"**{c.name}**" + (f", {c.legal_form}" if c.legal_form else ""))
    place = " ".join(x for x in (c.postal_code, c.city) if x)
    address = ", ".join(x for x in (c.address_line, place) if x)
    b.paragraph(address if c.address_line and place else todo("adresse de l'entreprise"))
    b.paragraph(f"SIRET {_siret(c.siret)}")
    contact = " · ".join(x for x in (c.phone, c.email) if x)
    if contact:
        b.paragraph(contact)

    b.heading("Client", 2)
    b.field("Client", d.client, "nom du client")
    if d.contact:
        b.field("À l'attention de", d.contact, "contact")
    b.field("Objet", d.subject, "objet")
    if d.reference:
        b.field("Référence", d.reference, "référence")

    b.heading("Prestations comprises", 1)
    if d.inclusions:
        b.bullets([f"{i['text']} ({i['file']}, p. {i['page']})" for i in d.inclusions])
        b.note("Chaque prestation renvoie au document du client et à sa page.")
    else:
        b.paragraph(
            "Les prestations des rubriques chiffrées ci-dessous, telles que décrites dans le "
            "dossier du client."
        )

    b.heading("Détail du prix", 1)
    t = d.table
    b.table(HEADERS, _rows(t.rows), WIDTHS)
    if t.has_totals:
        vat = vat_of(t.total_ht_cents, d.vat_bp)
        b.table(
            ("Montant", ""),
            [
                ["Total HT", money(t.total_ht_cents)],
                [f"TVA {vat_label(d.vat_bp)}", money(vat)],
                ["**Total TTC**", f"**{money(t.total_ht_cents + vat)}**"],
            ],
            (12.0, 4.6),
        )
    else:
        b.note("Prix unitaires HT : le montant sera établi selon les quantités commandées.")
    if t.options:
        b.heading("Options (non comprises dans le total)", 2)
        b.table(HEADERS, _rows(t.options), WIDTHS)
        if any(r.total_cents is not None for r in t.options):
            b.paragraph(f"Total des options HT : {money(t.options_cents)}")
    b.note(
        "Prix en euros hors taxes, établis d'après le dossier de consultation du client et ses "
        "quantités."
    )

    b.heading("Bon pour accord", 1)
    b.paragraph(signature_line(c.name, c.signatory_name, c.signatory_role))
    b.paragraph("Pour le client — date, nom et qualité du signataire, signature et cachet :")
    for _ in range(4):
        b.paragraph()
    return b
