"""Test files for the end-to-end journey: python fixtures.py <work dir>."""
import io, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
from tests.documents_helpers import make_pdf, make_docx
from openpyxl import Workbook
out = sys.argv[1]
rc = make_pdf([["REGLEMENT DE LA CONSULTATION", "Acheteur : Ville de Lyon", "Date limite de remise des offres"],
               ["Criteres : valeur technique 60 %, prix 40 %", "Plan impose du memoire : 1. Moyens 2. Methodologie"]])
cctp = make_pdf([["CAHIER DES CLAUSES TECHNIQUES PARTICULIERES", "Article 1 : nettoyage quotidien des bureaux avant 8h"],
                 ["Article 2 : vitrerie interieure une fois par trimestre", "Article 3 : produits ecolabellises"]])
# Chiffrage (ADR-049): the buyer's price file, a price per day with hours × rate beside it
dqe = Workbook(); ws = dqe.active; ws.title = "DQE"
ws["A3"] = "prestation quotidienne"
ws["A4"], ws["B4"], ws["C4"], ws["D4"], ws["I4"], ws["J4"] = "Site", "prix € HT/J", "nombre d'heures", "coût horaire HT", "Quantité", "Total HT"
ws["A5"], ws["B5"], ws["D5"], ws["H5"], ws["I5"], ws["J5"] = "Hôtel de ville", 0, 0, "=B5", 208, "=I5*H5"
ws["A6"], ws["B6"], ws["H6"], ws["I6"] = "Nuit (21h-6h)", 0, "=B6", 2
# an option priced « pour mémoire », out of the buyer's total
ws["A7"], ws["B7"], ws["H7"], ws["I7"], ws["J7"] = "OPTION : Vitrerie haute", 0, "=B7", 120, "=I7*H7"
ws["J8"] = "=SUM(J5:J6)"
dqe_buf = io.BytesIO(); dqe.save(dqe_buf)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("DCE/RC.pdf", rc); zf.writestr("DCE/CCTP.pdf", cctp)
    zf.writestr("DCE/DQE.xlsx", dqe_buf.getvalue())
    # ADR-051: the buyer's memoir frame, its boxes to fill
    import docx as _docx
    frame = _docx.Document()
    frame.add_heading("CADRE DE MEMOIRE TECHNIQUE", level=1)
    frame.add_paragraph("Nom du candidat : ………………………………")
    for title in ("1. Moyens humains et materiels", "2. Methodologie et organisation"):
        box = frame.add_table(rows=2, cols=1)
        box.rows[0].cells[0].text = title
        box.rows[1].cells[0].text = "- Ce que l'acheteur attend"
        frame.add_paragraph("")
    frame_buf = io.BytesIO(); frame.save(frame_buf)
    zf.writestr("DCE/Cadre de memoire technique.docx", frame_buf.getvalue())
open(f"{out}/DCE_mairie.zip", "wb").write(buf.getvalue())
# Consultations (ADR-052): a general contractor sends the whole lot; the company prices the cleaning
lot_cctp = make_pdf([["CCTP LOT 16 - PLATRERIE PEINTURE", "4. Platrerie : cloisons et doublages"],
                     ["12 NETTOYAGES", "Nettoyage avant OPR : sols, menuiseries, vitrages deux faces"],
                     ["Peinture acrylique mate des plafonds"]])
dpgf = Workbook(); ws = dpgf.active; ws.title = "DPGF"
ws["A3"], ws["D3"], ws["E3"], ws["F3"], ws["G3"] = "Désignation", "Unité", "Quantité", "PU HT", "Total HT"
ws["A4"] = "4 Plâtrerie"
ws["A5"], ws["D5"], ws["E5"], ws["F5"], ws["G5"] = "Cloisons", "m²", 300, None, "=E5*F5"
ws["A7"] = "12 Nettoyages"
ws["A8"], ws["D8"], ws["E8"], ws["F8"], ws["G8"] = "Nettoyage avant OPR", "m²", 2500, None, "=E8*F8"
ws["A9"], ws["D9"], ws["E9"], ws["F9"], ws["G9"] = "Nettoyage avant réception", "m²", 2500, None, "=E9*F9"
dpgf_buf = io.BytesIO(); dpgf.save(dpgf_buf)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("CCTP lot 16.pdf", lot_cctp); zf.writestr("DPGF lot 16.xlsx", dpgf_buf.getvalue())
    # 25/11: the request itself, read for the consultation's card (client, site, contact)
    zf.writestr("Demande de prix.pdf", make_pdf([[
        "ENTREPRISE GENERALE EXEMPLE - 12 rue des Lilas 69003 Lyon",
        "Demande de prix n EG-26-016",
        "Objet : Annexe du lycee - nettoyage",
        "Chantier : Lycee du Parc, 1 boulevard Anatole France 69006 Lyon",
        "Contact : Mme Exemple - contact@eg-exemple.fr - Tel 04 72 00 00 00"]]))
open(f"{out}/consultation.zip", "wb").write(buf.getvalue())
open(f"{out}/attestation_urssaf.pdf", "wb").write(make_pdf([["ATTESTATION DE VIGILANCE", "URSSAF Rhone-Alpes"]]))
open(f"{out}/memoire_2025.docx", "wb").write(make_docx([("Heading 1", "Moyens materiels"), ("Normal", "Nous utilisons des autolaveuses et des monobrosses professionnelles."), ("Normal", "Nous disposons de 3 autolaveuses Tennant T5 pour les grandes surfaces."), ("Normal", "Equipe : agents de service et 2 chefs d'equipe.")]))
wb = Workbook(); ws = wb.active
ws.append(["Client", "Type de client (public / privé)", "Objet du marché", "Lieu", "Département", "Montant (€ HT)", "Année"])
ws.append(["Mairie de Villeurbanne", "public", "Nettoyage des écoles", "Villeurbanne", 69, "85 000", 2024])
ws.append(["", "public", "Ligne sans client", None, None, None, None])
wb.save(f"{out}/references.xlsx")
# Staff and equipment lists (US-1.3): one line already in the profile, one new, one refused
wb = Workbook(); ws = wb.active
ws.append(["Qualification", "Nombre", "Précisions"])
ws.append(["Agent de service", 12, None])
ws.append(["Laveur de vitres", 3, "Travail en hauteur"])
ws.append(["Encadrant de site", "deux", None])
wb.save(f"{out}/moyens_humains.xlsx")
wb = Workbook(); ws = wb.active
ws.append(["Matériel", "Type de matériel", "Quantité"])
ws.append(["Monobrosse Taski Ergodisc", "monobrosse", 2])
ws.append(["Aspirateur Numatic", "aspirateur", 6])
wb.save(f"{out}/materiel.xlsx")
# Lot 4: in the local database of the journey, « Pilote » (100 credits a month) is the plan
# of a new sign-up, so the steps written before the credits have what they use.
import os
if os.environ.get("DATABASE_URL"):
    from sqlalchemy import create_engine, text
    with create_engine(os.environ["DATABASE_URL"]).begin() as conn:
        conn.execute(text("UPDATE plans SET is_default = false"))
        conn.execute(text("UPDATE plans SET is_default = true WHERE name = 'Pilote'"))
        # lot 5: every run starts from the server's settings (a previous run changed some)
        conn.execute(text("DELETE FROM platform_settings"))
print("fixtures ok")
