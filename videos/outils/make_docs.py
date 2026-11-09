"""Fictitious documents for the Pilao demo video: a DCE (RC + CCTP), an old memoir, attestations.

Every name, address and number here is invented (« Ville de Belmont-sur-Rhône », « Propreté Démo »).
"""

import io
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

from docx import Document
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
NAVY = HexColor("#1f3a5f")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=NAVY, fontSize=16, spaceAfter=10)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=NAVY, fontSize=12.5, spaceBefore=10)
P = ParagraphStyle("p", parent=ss["BodyText"], fontSize=10.5, leading=14.5, spaceAfter=6)
SMALL = ParagraphStyle("s", parent=P, fontSize=9, textColor=HexColor("#555555"))


def pdf(blocks: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm
    )
    story = []
    for b in blocks:
        if b == "PAGE":
            story.append(PageBreak())
        elif isinstance(b, tuple) and b[0] == "h1":
            story.append(Paragraph(b[1], H1))
        elif isinstance(b, tuple) and b[0] == "h2":
            story.append(Paragraph(b[1], H2))
        elif isinstance(b, tuple) and b[0] == "small":
            story.append(Paragraph(b[1], SMALL))
        elif isinstance(b, tuple) and b[0] == "table":
            t = Table(b[1], colWidths=b[2])
            t.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#999999")),
                        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e6eef8")),
                        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 8))
        else:
            story.append(Paragraph(b, P))
    doc.build(story)
    return buf.getvalue()


deadline = (date.today() + timedelta(days=21)).strftime("%d/%m/%Y")
questions = (date.today() + timedelta(days=12)).strftime("%d/%m/%Y")

RC = pdf(
    [
        ("small", "VILLE DE BELMONT-SUR-RHÔNE — Direction de la commande publique — 1 place de la Mairie, 69999 Belmont-sur-Rhône"),
        ("h1", "Règlement de la consultation"),
        "<b>Objet :</b> nettoyage et entretien des bâtiments communaux (hôtel de ville, médiathèque, deux groupes scolaires).",
        "<b>Procédure :</b> procédure adaptée (article R2123-1 du code de la commande publique).",
        "<b>Durée :</b> un an à compter du 1er février, reconductible trois fois par période d'un an.",
        "<b>Montant estimé :</b> 180 000 € HT par an.",
        f"<b>Date limite de réception des offres :</b> {deadline} à 12h00, sur la plateforme marches.belmont-demo.fr.",
        f"<b>Questions des candidats :</b> jusqu'au {questions}, par la plateforme.",
        "<b>Visite des sites :</b> obligatoire, sur rendez-vous auprès des services techniques. Une attestation de visite sera remise.",
        ("h2", "Article 5 — Critères de jugement des offres"),
        ("table", [["Critère", "Pondération"], ["Valeur technique (appréciée au vu du mémoire technique)", "60 %"], ["Prix des prestations", "40 %"]], [12 * cm, 4 * cm]),
        "La valeur technique est notée selon les sous-critères suivants : moyens humains et encadrement (20 %), méthodologie et organisation des prestations (25 %), démarche environnementale et produits (15 %).",
        "PAGE",
        ("h2", "Article 6 — Contenu du mémoire technique"),
        "Le candidat remet un mémoire technique de 15 pages maximum, structuré selon le plan suivant, qui s'impose :",
        "1. Moyens humains et encadrement",
        "2. Méthodologie et organisation des prestations",
        "3. Démarche environnementale et produits utilisés",
        "4. Contrôle qualité et continuité de service",
        ("h2", "Article 7 — Pièces à fournir"),
        "Au titre de la candidature : formulaires DC1 et DC2 (ou DUME), extrait Kbis de moins de trois mois, attestation de vigilance URSSAF de moins de six mois, attestation de régularité fiscale, attestation d'assurance responsabilité civile professionnelle en cours de validité.",
        "Au titre de l'offre : acte d'engagement, bordereau des prix unitaires complété, mémoire technique, attestation de visite.",
        ("h2", "Article 8 — Pénalités"),
        "Toute prestation non réalisée ou mal réalisée, constatée contradictoirement, donne lieu à une pénalité de 150 € par manquement. Le CCAP précise les modalités de reprise du personnel en place (article L1224-1 du code du travail et convention collective de la propreté, annexe 7).",
    ]
)

CCTP = pdf(
    [
        ("small", "VILLE DE BELMONT-SUR-RHÔNE — Nettoyage des bâtiments communaux"),
        ("h1", "Cahier des clauses techniques particulières"),
        ("h2", "Article 1 — Sites concernés"),
        ("table", [["Site", "Surface", "Fréquence"], ["Hôtel de ville", "1 450 m²", "Quotidienne, du lundi au vendredi"], ["Médiathèque", "980 m²", "Quotidienne, du mardi au samedi"], ["Groupe scolaire Les Tilleuls", "2 300 m²", "Quotidienne, jours d'école"], ["Groupe scolaire Jean-Moulin", "1 900 m²", "Quotidienne, jours d'école"]], [7 * cm, 3 * cm, 6.5 * cm]),
        ("h2", "Article 2 — Horaires d'intervention"),
        "Les prestations dans les bureaux de l'hôtel de ville sont réalisées avant 8h00 ou après 18h00. Dans les écoles, le nettoyage des classes est réalisé après 16h30 ; les sanitaires sont repassés à la pause méridienne.",
        ("h2", "Article 3 — Prestations attendues"),
        "Bureaux : vidage des corbeilles et tri sélectif, dépoussiérage des surfaces, aspiration des sols textiles, lavage des sols durs. Sanitaires : nettoyage et désinfection quotidiens, réapprovisionnement des consommables.",
        "PAGE",
        ("h2", "Article 4 — Vitrerie"),
        "Le nettoyage des vitres intérieures et extérieures accessibles est réalisé une fois par trimestre ; les vitres en hauteur nécessitent une nacelle, à la charge du titulaire.",
        ("h2", "Article 5 — Produits et démarche environnementale"),
        "Les produits utilisés sont écolabellisés (Ecolabel européen ou équivalent). Les fiches de données de sécurité sont tenues à la disposition de la Ville. Le titulaire privilégie le nettoyage à l'eau et aux microfibres et limite les emballages.",
        ("h2", "Article 6 — Encadrement et contrôle qualité"),
        "Le titulaire désigne un chef d'équipe joignable aux heures d'intervention et réalise un contrôle qualité mensuel contradictoire avec la Ville, sur une grille commune. Les absences du personnel sont remplacées dans la journée.",
        ("h2", "Article 7 — Remise en état estivale"),
        "Pendant les vacances d'été, le titulaire réalise la remise en état complète des groupes scolaires : décapage et protection des sols, lessivage des murs lavables et du mobilier.",
    ]
)

with zipfile.ZipFile(OUT / "DCE_Belmont_nettoyage.zip", "w") as z:
    z.writestr("DCE/RC_Belmont.pdf", RC)
    z.writestr("DCE/CCTP_Belmont.pdf", CCTP)
(OUT / "RC_Belmont.pdf").write_bytes(RC)

# An old memoir of the fictitious company, to show the profile pre-fill.
m = Document()
m.add_heading("Mémoire technique — Nettoyage des locaux de la CCI Démo (2024)", level=1)
m.add_heading("1. Nos moyens humains", level=2)
m.add_paragraph("Propreté Démo emploie 24 agents de propreté, encadrés par 3 chefs d'équipe et un responsable d'exploitation.")
m.add_paragraph("Tous nos agents sont formés aux gestes et postures et à l'utilisation des produits.")
m.add_heading("2. Notre matériel", level=2)
m.add_paragraph("Nous disposons de 4 autolaveuses Nilfisk SC450 pour les grandes surfaces.")
m.add_paragraph("Notre parc compte aussi 6 monobrosses Taski Ergodisc et 15 aspirateurs à poussière Numatic.")
m.add_paragraph("Une nacelle élévatrice est louée pour la vitrerie en hauteur.")
m.add_heading("3. Nos références", level=2)
m.add_paragraph("Syndicat des collèges de l'Est : nettoyage de six collèges, depuis 2021.")
m.add_paragraph("Clinique du Parc Démo : bionettoyage des chambres et blocs, 2022 à 2024.")
m.add_heading("4. Qualité", level=2)
m.add_paragraph("Notre entreprise est certifiée ISO 9001 depuis 2020 et détient la qualification Qualipropre.")
buf = io.BytesIO()
m.save(buf)
(OUT / "Memoire_CCI_2024.docx").write_bytes(buf.getvalue())

today = date.today()
att = [
    (
        "Attestation_URSSAF.pdf",
        [
            ("h1", "Attestation de vigilance"),
            "URSSAF Rhône-Alpes (document de démonstration)",
            "Entreprise : PROPRETÉ DÉMO — SIREN 912 345 674",
            f"Délivrée le {(today - timedelta(days=40)).strftime('%d/%m/%Y')}.",
            "L'entreprise est à jour de ses obligations de déclaration et de paiement.",
        ],
    ),
    (
        "Kbis_Proprete_Demo.pdf",
        [
            ("h1", "Extrait Kbis"),
            "Greffe du tribunal de commerce de Lyon (document de démonstration)",
            "Dénomination : PROPRETÉ DÉMO — SIREN 912 345 674",
            f"Extrait délivré le {(today - timedelta(days=100)).strftime('%d/%m/%Y')}.",
        ],
    ),
]
for name, blocks in att:
    (OUT / name).write_bytes(pdf(blocks))
print("documents ok")
