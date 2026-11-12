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
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("DCE/RC.pdf", rc); zf.writestr("DCE/CCTP.pdf", cctp)
open(f"{out}/DCE_mairie.zip", "wb").write(buf.getvalue())
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
