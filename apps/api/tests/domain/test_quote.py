"""The company's quote for a consultation (ADR-052): pure rules."""

from decimal import Decimal

from app.domain.pricing import LinePrice, Priced, PriceLine
from app.domain.quote import (
    InclusionIn,
    Page,
    keep_sourced,
    pick_pages,
    quote_table,
    terms,
    vat_of,
)


def line(
    lid: str, section: str, label: str, unit: str, qty: str | None, option: bool = False
) -> PriceLine:
    return PriceLine(
        id=lid,
        sheet="DPGF",
        section=section,
        label=label,
        unit=unit,
        quantity=Decimal(qty) if qty is not None else None,
        price_cell=lid.split("!")[1],
        hours_cell=None,
        rate_cell=None,
        hourly=False,
        surcharge="none",
        option=option,
    )


def price(lid: str, cents: int | None, total: int | None, source: str = "price") -> LinePrice:
    return LinePrice(lid, None, None, cents, total, source)  # type: ignore[arg-type]


CCTP = [
    Page("CCTP lot 16.pdf", 3, "Article 4.2 Plâtrerie : cloisons, doublages, bandes et enduits."),
    Page(
        "CCTP lot 16.pdf",
        41,
        "12 NETTOYAGES. Nettoyage de fin de chantier avant OPR : sols, menuiseries, vitrages "
        "deux faces, évacuation des déchets en benne.",
    ),
    Page("CCTP lot 16.pdf", 42, "Nettoyage avant réception : dépoussiérage complet des locaux."),
    Page("CCTP lot 16.pdf", 7, "Peinture acrylique mate sur plafonds."),
]


def test_terms_are_the_words_that_name_the_work() -> None:
    found = terms(["12 Nettoyages", "Nettoyage avant OPR", "Nettoyage avant réception"])
    assert "nettoyage" in found and "reception" in found
    assert "avant" not in found  # a word that names nothing
    assert len(found) == len(set(found))


def test_the_pages_sent_are_those_of_the_rubriques_priced() -> None:
    sent = pick_pages(CCTP, terms(["12 Nettoyages", "Nettoyage avant OPR"]))
    assert [(p.file, p.page) for p in sent] == [("CCTP lot 16.pdf", 41), ("CCTP lot 16.pdf", 42)]


def test_no_page_mentions_the_work_then_none_is_sent() -> None:
    assert pick_pages(CCTP, terms(["Shampouinage moquette"])) == []


def test_the_pages_sent_stay_within_the_limits() -> None:
    many = [Page("CCTP.pdf", n, "nettoyage " * 400) for n in range(1, 40)]
    sent = pick_pages(many, ["nettoyage"], max_pages=5, max_chars=10_000)
    assert 1 <= len(sent) <= 5
    assert sum(len(p.text) for p in sent) <= 10_000
    assert [p.page for p in sent] == sorted(p.page for p in sent)  # in the document's order


def test_only_bullets_citing_a_page_sent_are_kept() -> None:
    sent = CCTP[1:3]
    proposed = [
        InclusionIn(text="Nettoyage des sols et des menuiseries avant OPR", file="CCTP lot 16.pdf",
                    page=41),
        InclusionIn(text="Vitrerie deux faces", file="CCTP lot 16.pdf", page=41),
        InclusionIn(text="Remise en peinture", file="CCTP lot 16.pdf", page=7),  # not sent
        InclusionIn(text="Gardiennage du chantier", file="Autre.pdf", page=41),  # not sent
        InclusionIn(text="  vitrerie deux faces ", file="CCTP lot 16.pdf", page=42),  # twice
        InclusionIn(text="   ", file="CCTP lot 16.pdf", page=42),
    ]  # fmt: skip
    kept = keep_sourced(proposed, sent)
    assert kept == [
        {"text": "Nettoyage des sols et des menuiseries avant OPR", "file": "CCTP lot 16.pdf",
         "page": 41},
        {"text": "Vitrerie deux faces", "file": "CCTP lot 16.pdf", "page": 41},
    ]  # fmt: skip


def test_vat_is_rounded_to_the_cent() -> None:
    assert vat_of(1_000_000, 2000) == 200_000
    assert vat_of(333, 2000) == 67  # 66,6 → 67
    assert vat_of(1_000, 550) == 55
    assert vat_of(1_000, 0) == 0


def test_the_table_keeps_the_rubriques_priced_and_puts_options_apart() -> None:
    lines = [
        line("DPGF!F10", "12.1 Nettoyage avant OPR", "Bâtiment A", "m²", "1250"),
        line("DPGF!F11", "12.1 Nettoyage avant OPR", "Bâtiment B", "m²", "800"),
        line("DPGF!F20", "4 Plâtrerie", "Cloisons", "m²", "300"),
        line("DPGF!F30", "12.3 Options", "Vitrerie haute", "m²", "100", option=True),
        line("DPGF!F40", "12.2 Bordereau", "Heure de régie", "heure", None),
    ]
    priced = Priced(
        lines=[
            price("DPGF!F10", 150, 187_500),
            price("DPGF!F11", 150, 120_000),
            price("DPGF!F20", None, None, "excluded"),
            price("DPGF!F30", 300, 30_000),
            price("DPGF!F40", 3500, None),
        ],
        total_cents=307_500,
        missing_count=0,
        options_cents=30_000,
    )
    table = quote_table(lines, priced)
    assert [(r.section, r.label) for r in table.rows] == [
        ("12.1 Nettoyage avant OPR", "Bâtiment A"),
        ("12.1 Nettoyage avant OPR", "Bâtiment B"),
        ("12.2 Bordereau", "Heure de régie"),
    ]
    assert table.rows[2].total_cents is None  # a unit price, no quantity
    assert [r.label for r in table.options] == ["Vitrerie haute"]
    assert (table.total_ht_cents, table.options_cents) == (307_500, 30_000)
    assert table.has_totals


def test_the_fingerprint_changes_with_any_price_or_quantity() -> None:
    from app.domain.quote import QuoteRow, QuoteTable, fingerprint

    row = QuoteRow("12 Nettoyages", "Avant OPR", "m²", Decimal(2500), 150, 375_000)
    base = fingerprint(QuoteTable([row], [], 375_000, 0))
    assert base == fingerprint(QuoteTable([row], [], 375_000, 0))
    other = QuoteRow("12 Nettoyages", "Avant OPR", "m²", Decimal(2500), 160, 400_000)
    assert base != fingerprint(QuoteTable([other], [], 400_000, 0))
    assert base != fingerprint(QuoteTable([row], [row], 375_000, 375_000))


def test_the_signature_line_names_a_person_or_leaves_a_line_to_fill() -> None:
    from app.domain.quote import signature_line

    assert signature_line("ENG-PRO (E.P.)", "ENG-PRO", "ENG-PRO") == (
        "Pour ENG-PRO (E.P.) — nom et qualité du signataire :"
    )
    assert signature_line("ENG PRO", "Abdraouf Exemple", "Gérant") == (
        "Pour ENG PRO : Abdraouf Exemple, Gérant"
    )
    assert signature_line("ENG PRO", "Abdraouf Exemple", "eng-pro") == (
        "Pour ENG PRO : Abdraouf Exemple"
    )
    assert signature_line("ENG PRO", None, None) == (
        "Pour ENG PRO — nom et qualité du signataire :"
    )
