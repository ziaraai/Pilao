"""Filling the buyer's memoir frame (ADR-051): its own file, each answer under its box."""

import io
from datetime import datetime

from docx import Document
from docx.enum.text import WD_COLOR_INDEX

from app.exports.frame_docx import fill_frame
from app.exports.memoir_docx import Chapter, MemoirExportData


def rillieux_frame() -> bytes:
    """The shape of the 26020M frame: a cover with the candidate's name to write, a title,
    then three boxes (title row, expectations row), empty lines after each, a footer."""
    doc = Document()
    doc.add_heading("CADRE DE MÉMOIRE TECHNIQUE ET ENVIRONNEMENTAL", level=1)
    doc.add_paragraph("Nom du candidat : ………………………………………")
    doc.add_paragraph("(à compléter par le candidat)")
    doc.add_paragraph("Valeur technique")
    for title, expected in (
        ("Sous-critère 1.1 : Pertinence de la méthodologie", "– Protocole de nettoyage ;"),
        ("Sous-critère 1.2 : Pertinence des moyens humains", "- Organisation du travail ;"),
        ("Performances en matière de protection de l'environnement (10 points)", "– Écolabel"),
    ):
        box = doc.add_table(rows=2, cols=1)
        box.rows[0].cells[0].text = title
        box.rows[1].cells[0].text = expected
        doc.add_paragraph("")
    doc.sections[0].footer.paragraphs[0].text = "26020M - CMTE"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def data(chapters: list[Chapter]) -> MemoirExportData:
    return MemoirExportData(
        company="ENG PRO",
        tender_title="Nettoyage des gymnases",
        buyer="Ville de Rillieux-la-Pape",
        reference="26020M",
        lot=None,
        version=1,
        exported_at=datetime(2026, 11, 16, 10, 0),
        chapters=chapters,
    )


CHAPTERS = [
    Chapter(
        "Sous-critère 1.1 : Pertinence de la méthodologie",
        "## Sous-critère 1.1 : Pertinence de la méthodologie\n\nNous lavons les sols **chaque jour**."
        "\n\n### Nos engagements\n\n- Passage avant 8 h.\n\n| Site | Fréquence |\n|---|---|\n"
        "| COSEC | quotidienne |\n",
    ),
    Chapter(
        "Sous-critère 1.2 : Pertinence des moyens humains",
        "## Sous-critère 1.2 : Pertinence des moyens humains\n\n"
        "Chef d'équipe : [À COMPLÉTER : nom du chef d'équipe].",
    ),
    Chapter(
        "Critère n° 3 Démarche en faveur du développement durable",
        "## Critère n° 3 Démarche en faveur du développement durable\n\nProduits écolabellisés.",
    ),
    Chapter("Planning de démarrage", "## Planning de démarrage\n\nVisite des sites."),
]


def body_texts(doc: Document) -> list[str]:
    """The body in order, a table counted by its first cell."""
    out: list[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            out.append("".join(t.text or "" for t in child.iter() if t.tag.endswith("}t")))
        elif tag == "tbl":
            first = next(c for c in child.iter() if c.tag.endswith("}tc"))
            out.append(
                "[table] " + "".join(t.text or "" for t in first.iter() if t.tag.endswith("}t"))
            )
    return [t for t in out if t.strip()]


def test_answers_go_under_their_boxes_in_the_buyers_file() -> None:
    result = fill_frame(rillieux_frame(), data(CHAPTERS))
    doc = Document(io.BytesIO(result.content))
    texts = body_texts(doc)
    i11 = texts.index("[table] Sous-critère 1.1 : Pertinence de la méthodologie")
    i12 = texts.index("[table] Sous-critère 1.2 : Pertinence des moyens humains")
    ienv = texts.index(
        "[table] Performances en matière de protection de l'environnement (10 points)"
    )
    answer11 = texts.index("Nous lavons les sols chaque jour.")
    assert i11 < answer11 < i12  # the 1.1 answer right under its box
    assert (
        "Nos engagements" in texts[answer11:i12] and "• Passage avant 8 h." in texts[answer11:i12]
    )
    assert "[table] Site" in texts[answer11:i12]  # its table too
    assert i12 < texts.index("Chef d'équipe : [À COMPLÉTER : nom du chef d'équipe].") < ienv
    assert ienv < texts.index("Produits écolabellisés.")
    # the box already holds the title: it is not written again under it
    assert texts.count("Sous-critère 1.1 : Pertinence de la méthodologie") == 0
    # a chapter with no box: at the end, under its own title
    assert texts[-2:] == ["Planning de démarrage", "Visite des sites."]
    assert any("Planning de démarrage" in w and "fin" in w for w in result.warnings)
    assert any("Critère n° 3" in w and "ordre" in w for w in result.warnings)


def test_candidate_name_and_buyer_layout_kept() -> None:
    result = fill_frame(rillieux_frame(), data(CHAPTERS))
    doc = Document(io.BytesIO(result.content))
    texts = body_texts(doc)
    assert "Nom du candidat : ENG PRO" in texts
    assert "(à compléter par le candidat)" in texts
    assert doc.sections[0].footer.paragraphs[0].text == "26020M - CMTE"
    marks = [r for p in doc.paragraphs for r in p.runs if r.text.startswith("[À COMPLÉTER")]
    assert marks and all(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in marks)
    assert result.to_complete == ["nom du chef d'équipe"]


def test_imposed_font_applied_to_the_answers_only() -> None:
    chapters = [CHAPTERS[0]]
    d = data(chapters)
    d.font, d.font_size = "Times New Roman", 11
    doc = Document(io.BytesIO(fill_frame(rillieux_frame(), d).content))
    answer = next(p for p in doc.paragraphs if p.text == "Nous lavons les sols chaque jour.")
    assert all(r.font.name == "Times New Roman" for r in answer.runs)
    title = next(p for p in doc.paragraphs if p.text.startswith("CADRE DE MÉMOIRE"))
    assert all(r.font.name != "Times New Roman" for r in title.runs)  # the buyer's text untouched
