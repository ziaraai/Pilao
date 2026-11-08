import io

import pytest

from app.documents.chunk import MAX_TOKENS, chunk_blocks, estimate_tokens
from app.documents.extract import (
    Block,
    ExtractionError,
    extract_docx,
    extract_pdf,
    looks_like_heading,
)
from tests.documents_helpers import make_blank_pdf, make_docx, make_pdf


def test_heading_heuristics() -> None:
    for yes in [
        "1. Présentation de l'entreprise",
        "2.3 Moyens humains",
        "ARTICLE 5 - Durée",
        "MOYENS MATÉRIELS",
        "Chapitre 2 : Méthodologie",
    ]:
        assert looks_like_heading(yes), yes
    for no in [
        "Nous intervenons chaque jour dans les locaux, avec soin,",
        "1 000 euros",
        "",
        "a" * 200,
        "Le titulaire s'engage à respecter les délais.",
    ]:
        assert not looks_like_heading(no), no


def test_pdf_pages_headings_and_text() -> None:
    pdf = make_pdf(
        [
            [
                "1. Presentation de l'entreprise",
                "",
                "Nous sommes une PME de nettoyage creee en 2010.",
            ],
            ["2. Moyens humains", "", "Nous employons douze agents de service qualifies."],
        ]
    )
    blocks = extract_pdf(io.BytesIO(pdf))
    headings = [(b.text, b.page) for b in blocks if b.kind == "heading"]
    assert headings == [("1. Presentation de l'entreprise", 1), ("2. Moyens humains", 2)]
    assert any("douze agents" in b.text and b.page == 2 for b in blocks)


def test_scanned_pdf_is_reported_not_indexed_empty() -> None:
    with pytest.raises(ExtractionError, match="scan"):
        extract_pdf(io.BytesIO(make_blank_pdf()))


def test_corrupt_pdf() -> None:
    with pytest.raises(ExtractionError, match="PDF"):
        extract_pdf(io.BytesIO(b"%PDF-1.4 this is not really a pdf"))


def test_docx_headings_paragraphs_and_tables() -> None:
    data = make_docx(
        [("Heading 1", "Moyens"), ("Normal", "Nous disposons de 3 autolaveuses.")],
        table=[["Matériel", "Quantité"], ["Autolaveuse", "3"]],
    )
    blocks = extract_docx(io.BytesIO(data))
    assert blocks[0] == Block("heading", "Moyens", None)
    assert any("autolaveuses" in b.text for b in blocks)
    assert any(b.text == "Autolaveuse | 3" for b in blocks)


def test_docx_titles_without_heading_styles() -> None:
    """As in a real memoir (ENG PRO, 2017, written in LibreOffice): every paragraph is
    « Normal »; the titles are numbered with a dash, or in bold."""
    from docx import Document

    doc = Document()
    for text in (
        "MEMOIRE TECHNIQUE",
        "1 – PRESENTATION",
        "2 - Moyens en Matériel",
        "2.1 -  Description du matériel de l 'entreprise",
        "3 auto porter de marque TENANTE 7300",  # a list: a number, no dash
        "42000 SAINT ETIENNE",
        "1. Le titulaire assure le nettoyage quotidien des bureaux avant 8 heures.",
        "II. Annexes",
    ):
        doc.add_paragraph(text)
    para = doc.add_paragraph()
    para.add_run("Définir les fréquences").bold = True
    long = doc.add_paragraph()
    long.add_run("Une phrase entière en gras ne fait pas un titre, même courte.").bold = True
    out = io.BytesIO()
    doc.save(out)
    kinds = {b.text: b.kind for b in extract_docx(io.BytesIO(out.getvalue()))}
    assert [t for t, k in kinds.items() if k == "heading"] == [
        "1 – PRESENTATION",
        "2 - Moyens en Matériel",
        "2.1 -  Description du matériel de l 'entreprise",
        "II. Annexes",
        "Définir les fréquences",
    ]


def test_docx_empty_and_corrupt() -> None:
    with pytest.raises(ExtractionError, match="aucun texte"):
        extract_docx(io.BytesIO(make_docx([])))
    with pytest.raises(ExtractionError, match="Word"):
        extract_docx(io.BytesIO(b"PK not a docx"))


def words(n: int, tag: str = "mot") -> str:
    return " ".join(f"{tag}{i}" for i in range(n))


def test_chunks_respect_size_overlap_and_pages() -> None:
    blocks = [Block("heading", "1. Méthode", 1)]
    blocks += [Block("paragraph", words(120, f"p{i}x"), 1 + i // 4) for i in range(24)]
    chunks = chunk_blocks(blocks)
    assert len(chunks) > 2
    assert all(c.tokens <= MAX_TOKENS for c in chunks)
    assert all(c.heading == "1. Méthode" for c in chunks)
    assert chunks[0].page_from == 1 and chunks[-1].page_to == 6
    # overlap: the start of a chunk repeats the end of the previous one
    first_tail = chunks[0].content.split()[-5:]
    assert all(w in chunks[1].content for w in first_tail)
    # nothing is lost: every word appears in at least one chunk
    joined = " ".join(c.content for c in chunks)
    assert all(f"p{i}x119" in joined for i in range(24))


def test_new_heading_starts_a_new_chunk_without_overlap() -> None:
    blocks = [
        Block("heading", "A", 1),
        Block("paragraph", "alpha " * 40, 1),
        Block("heading", "B", 2),
        Block("paragraph", "beta " * 40, 2),
    ]
    chunks = chunk_blocks(blocks)
    assert [(c.heading, c.page_from) for c in chunks] == [("A", 1), ("B", 2)]
    assert "alpha" not in chunks[1].content


def test_huge_paragraph_without_punctuation_is_split() -> None:
    chunks = chunk_blocks([Block("paragraph", "mot " * 5000, 1)])
    assert len(chunks) > 3 and all(c.tokens <= MAX_TOKENS for c in chunks)


def test_empty_and_tiny_inputs() -> None:
    assert chunk_blocks([]) == []
    only = chunk_blocks([Block("paragraph", "Court.", None)])
    assert (
        len(only) == 1 and only[0].page_from is None and only[0].tokens == estimate_tokens("Court.")
    )


def test_pdf_lines_of_a_paragraph_are_rejoined_and_dehyphenated() -> None:
    pdf = make_pdf([["Le prestataire assure l'entre-", "tien des locaux chaque jour", "ouvre."]])
    blocks = extract_pdf(io.BytesIO(pdf))
    assert [b.text for b in blocks] == [
        "Le prestataire assure l'entretien des locaux chaque jour ouvre."
    ]


def test_long_unpunctuated_sentence_keeps_the_text_order() -> None:
    from app.documents.chunk import _split_long

    text = "Courte phrase. " + " ".join(f"mot{i}" for i in range(1500))
    pieces = _split_long(text)
    assert pieces[0] == "Courte phrase."
    assert " ".join(pieces).split() == text.split()


def test_overlap_keeps_the_page_it_comes_from() -> None:
    para = " ".join(["Texte de la page."] * 120)  # about 2000 characters per page
    chunks = chunk_blocks([Block("paragraph", para, 3), Block("paragraph", para, 4)])
    assert len(chunks) == 2
    assert (chunks[1].page_from, chunks[1].page_to) == (3, 4)


def test_docx_size_limit_counts_every_table_row(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.documents import extract

    monkeypatch.setattr(extract, "MAX_CHARS", 500)
    rows = [[f"ligne {i} " + "x" * 40, "valeur"] for i in range(30)]
    with pytest.raises(ExtractionError):
        extract_docx(io.BytesIO(make_docx([("Normal", "Intro")], table=rows)))
