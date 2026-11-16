"""Buyer's memoir frame (ADR-051): which chapter goes under which box of the frame."""

from app.domain.frame import is_frame_name, match_chapters, plain_name

# The outline drafted for Rillieux (RC criteria) and the frame's boxes, as they really are
CHAPTERS = [
    "Critère n° 1 Valeur technique analysée au regard du mémoire technique remis par le candidat",
    "Sous-critère 1.1 : Pertinence de la méthodologie employée au regard des prescriptions du CCTP",
    "Sous-critère 1.2 : Pertinence des moyens humains affectés à la réalisation des prestations du marché",
    "Critère n° 3 Démarche en faveur du développement durable au regard du mémoire technique remis par le candidat",
]
ANCHORS = [
    "CADRE DE MÉMOIRE TECHNIQUE ET ENVIRONNEMENTAL",
    "Entretien et nettoyage des bâtiments sportifs de la Ville de Rillieux-la-Pape (69140)",
    "Valeur technique",
    "Sous-critère 1.1 : Pertinence de la méthodologie employée au regard des prescriptions du CCTP",
    "Sous-critère 1.2 : Pertinence des moyens humains affectés à la réalisation des prestations du marché",
    "Performances en matière de protection de l'environnement analysée au regard du mémoire technique remis par le candidat (10 points)",
]


def test_rillieux_chapters_go_under_their_boxes() -> None:
    matched = match_chapters(CHAPTERS, ANCHORS, boxes=[3, 4, 5])
    # « Valeur technique » for the criterion, each sub-criterion under its box, and the
    # environment box for the sustainable development criterion (paired by order)
    assert [m.anchor for m in matched] == [2, 3, 4, 5]
    assert [m.uncertain for m in matched] == [False, False, False, True]


def test_same_titles_match_exactly() -> None:
    titles = ["Sous-critère 1.1 : Méthodologie", "Sous-critère 1.2 : Moyens humains"]
    assert [m.anchor for m in match_chapters(titles, titles, boxes=[0, 1])] == [0, 1]


def test_a_chapter_without_its_box_is_left_out() -> None:
    matched = match_chapters(
        ["Moyens humains", "Planning de démarrage", "Démarche qualité"],
        ["Moyens humains affectés", "Démarche qualité et contrôle"],
        boxes=[0, 1],
    )
    assert [m.anchor for m in matched] == [0, None, 1]


def test_order_is_kept() -> None:
    """A later chapter never goes above an earlier one's box."""
    matched = match_chapters(
        ["Méthodologie de nettoyage", "Moyens humains"],
        ["Moyens humains", "Méthodologie de nettoyage"],
        boxes=[0, 1],
    )
    placed = [m.anchor for m in matched if m.anchor is not None]
    assert placed == sorted(placed)


def test_frame_file_names() -> None:
    assert plain_name("DCE_26020M/26020M_M#U00e9moire technique et environnemenal.docx") == (
        "26020m mémoire technique et environnemenal"
    )
    assert is_frame_name("DCE_26020M/26020M_M#U00e9moire technique et environnemenal.docx")
    assert is_frame_name("Cadre de réponse technique.docx")
    assert is_frame_name("CRT_lot1.docx") is False
    assert not is_frame_name("26020M_CCTP_prestations.pdf")
    assert not is_frame_name("Mémoire technique.pdf")  # a PDF frame cannot be filled


def test_the_real_drafted_titles_of_rillieux() -> None:
    """The memoir drafted in prod had a shorter 4th title: « remis par le candidat » was left
    in the 1st only and pulled it towards the environment box. The 1st chapter still goes
    under « Valeur technique », found in its gap before the first box."""
    chapters = [
        *CHAPTERS[:3],
        "Critère n° 3 Démarche en faveur du développement durable au regard du mémoire technique",
    ]
    anchors = [
        *ANCHORS[:2],
        "Nom du candidat : ENG PRO",
        "(à compléter par le candidat)",
        *ANCHORS[2:],
    ]
    matched = match_chapters(chapters, anchors, boxes=[5, 6, 7])
    assert [m.anchor for m in matched] == [4, 5, 6, 7]
