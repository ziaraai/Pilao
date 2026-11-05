"""Pre-filled documents of a bid (US-4.5): DC1, DC2, means, references, schedule outline.

Pure functions from a :class:`FormData` snapshot to a Word document. Everything comes from
the company's profile or from the analysed DCE (with its source); whatever is missing is
written ``[À COMPLÉTER : …]``. Boxes the company must tick itself (alone or grouped,
receivership, sworn statements) are left empty: Pilao never attests on its behalf.

DC1 and DC2 follow the headings of the forms of the Direction des affaires juridiques
(DAJ) of the Ministry of the Economy; question Q12 tracks their check against the official
version in force.
"""

from dataclasses import dataclass, field
from datetime import date

from app.exports.docx_builder import DocBuilder, todo

MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
CLEANING_TRADES = {"nettoyage_locaux", "vitrerie", "remise_en_etat", "hygiene"}
PROOF_LABELS = {
    "kbis": "Extrait Kbis",
    "rne_certificate": "Attestation d'immatriculation au RNE",
    "urssaf_vigilance": "Attestation de vigilance URSSAF",
    "tax_compliance": "Attestation de régularité fiscale",
    "cibtp_certificate": "Certificat CIBTP",
    "insurance_rc_pro": "Attestation d'assurance responsabilité civile professionnelle",
    "insurance_decennale": "Attestation d'assurance décennale",
    "qualification": "Qualification / certification",
    "other": "Autre document",
}


@dataclass(frozen=True)
class Sourced:
    value: str | None
    source: str | None = None  # "DCE/RC.pdf p. 2"


@dataclass(frozen=True)
class Company:
    name: str
    siret: str
    siren: str
    vat_number: str
    legal_form: str | None = None
    address: str | None = None
    naf_code: str | None = None
    phone: str | None = None
    email: str | None = None
    signatory_name: str | None = None
    signatory_role: str | None = None
    headcount_range: str | None = None


@dataclass(frozen=True)
class ReferenceRow:
    client: str
    public: bool
    title: str
    location: str | None
    year: int | None
    amount_cents: int | None
    duration_months: int | None
    description: str | None


@dataclass
class FormData:
    company: Company
    buyer: Sourced
    title: Sourced
    reference: str | None = None
    lot: str | None = None
    lots: list[str] = field(default_factory=list)
    deadline: Sourced = field(default_factory=lambda: Sourced(None))
    duration: Sourced = field(default_factory=lambda: Sourced(None))
    site_visit: Sourced = field(default_factory=lambda: Sourced(None))
    revenues_cents: list[int | None] = field(default_factory=list)  # N-1, N-2, N-3
    staff: list[tuple[str, int, str | None]] = field(default_factory=list)
    equipment: list[tuple[str, str | None, int | None]] = field(default_factory=list)
    certifications: list[tuple[str, str | None, date | None]] = field(default_factory=list)
    references: list[ReferenceRow] = field(default_factory=list)
    proofs: list[tuple[str, date | None]] = field(default_factory=list)  # usable vault docs
    trades: list[str] = field(default_factory=list)
    brand_color: str | None = None
    logo: bytes | None = None


def eur(cents: int | None) -> str | None:
    if cents is None:
        return None
    return f"{round(cents / 100):,}".replace(",", " ") + " € HT"


def french_date(d: date | None) -> str | None:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}" if d else None


def _builder(data: FormData, title: str, subtitle: str) -> DocBuilder:
    b = DocBuilder(brand_color=data.brand_color, logo=data.logo, company=data.company.name)
    b.header_footer(data.company.name, "Document pré-rempli par Pilao, à vérifier")
    b.title(title, subtitle)
    return b


def _tender(b: DocBuilder, data: FormData) -> None:
    b.heading("Identification de l'acheteur")
    b.field("Acheteur", data.buyer.value, "nom de l'acheteur", data.buyer.source)
    b.heading("Objet de la consultation")
    b.field("Objet", data.title.value, "objet de la consultation", data.title.source)
    b.field("Référence de la consultation", data.reference, "référence donnée par l'acheteur")


def _identity(b: DocBuilder, c: Company, vat: bool = False) -> None:
    b.field("Dénomination sociale", c.name, "dénomination sociale")
    b.field("Forme juridique", c.legal_form, "forme juridique")
    b.field("Adresse du siège", c.address, "adresse du siège social")
    b.field("SIRET", c.siret, "numéro SIRET")
    b.field("Code NAF", c.naf_code, "code NAF")
    if vat:
        b.field("N° de TVA intracommunautaire (calculé depuis le SIREN)", c.vat_number, "TVA")
    b.field("Téléphone", c.phone, "téléphone (Profil > Identité)")
    b.field("Adresse électronique", c.email, "adresse électronique (Profil > Identité)")


def _signature(b: DocBuilder, c: Company) -> None:
    b.heading("Signature")
    signatory = ", ".join(x for x in (c.signatory_name, c.signatory_role) if x) or None
    b.field(
        "Nom, prénom et qualité du signataire",
        signatory,
        "personne habilitée à engager l'entreprise",
    )
    b.field("Lieu et date", None, "lieu et date de signature")
    b.paragraph("Signature :")
    b.paragraph()
    b.note("À signer par une personne habilitée à engager l'entreprise.")


def dc1(data: FormData) -> DocBuilder:
    b = _builder(data, "DC1 — Lettre de candidature", data.title.value or "")
    b.note(
        "Pré-rempli par Pilao d'après votre profil et le DCE, sur la trame du formulaire DC1 "
        "du ministère de l'Économie. Vérifiez-le, complétez les « [À COMPLÉTER] », cochez les "
        "cases et signez. Si l'acheteur impose son propre formulaire ou le DUME, utilisez-le."
    )
    _tender(b, data)
    b.heading("Objet de la candidature")
    b.paragraph("La candidature est présentée :")
    if data.lots:
        b.checkboxes("pour le marché public (sans lot)", "pour tous les lots")
        b.paragraph("☐ pour le ou les lots suivants :")
        b.bullets([f"☐ {lot}" for lot in data.lots])
    else:
        b.checkboxes("pour le marché public", "pour le ou les lots :")
    b.field("Lot visé", data.lot, "lot(s) visé(s), le cas échéant")
    b.heading("Présentation du candidat")
    b.checkboxes("Le candidat se présente seul", "Le candidat est un groupement d'entreprises")
    b.paragraph("En cas de groupement :")
    b.checkboxes("conjoint", "solidaire")
    b.heading("Identification du candidat")
    _identity(b, data.company)
    b.heading("Engagements du candidat")
    b.paragraph(
        "☐ Le candidat déclare sur l'honneur n'entrer dans aucun des cas d'interdiction de "
        "soumissionner prévus aux articles L. 2141-1 à L. 2141-5 et L. 2141-7 à L. 2141-11 du "
        "code de la commande publique, et être en règle au regard des articles L. 5212-1 à "
        "L. 5212-11 du code du travail concernant l'emploi des travailleurs handicapés."
    )
    b.note("Cette déclaration engage l'entreprise : c'est à elle de cocher la case.")
    _signature(b, data.company)
    return b


def dc2(data: FormData) -> DocBuilder:
    b = _builder(data, "DC2 — Déclaration du candidat", data.title.value or "")
    b.note(
        "Pré-rempli par Pilao d'après votre profil, sur la trame du formulaire DC2 du ministère "
        "de l'Économie. Les mêmes données servent à remplir le DUME en ligne si l'acheteur le "
        "demande."
    )
    _tender(b, data)
    b.heading("Identification du candidat")
    _identity(b, data.company, vat=True)
    b.heading("Situation juridique")
    b.paragraph("Le candidat est-il en redressement judiciaire ?")
    b.checkboxes("Oui (joindre la copie du jugement)", "Non")
    b.heading("Capacité économique et financière")
    revenues = (data.revenues_cents + [None, None, None])[:3]
    b.table(
        ["Exercice", "Chiffre d'affaires global HT", "Part concernant l'objet du marché"],
        [
            [
                f"N-{i + 1} (du … au …)",
                eur(cents) or todo(f"chiffre d'affaires N-{i + 1}"),
                todo("part du chiffre d'affaires"),
            ]
            for i, cents in enumerate(revenues)
        ],
        widths_cm=(4.5, 6, 6),
    )
    b.heading("Capacité technique et professionnelle")
    total = sum(count for _, count, _ in data.staff)
    b.field(
        "Moyens humains déclarés",
        (
            f"{total} personne{'s' if total > 1 else ''} (détail dans la liste des moyens humains)"
            if data.staff
            else None
        ),
        "effectif affecté (Profil > Moyens humains)",
    )
    b.field("Tranche d'effectif (répertoire SIRENE)", data.company.headcount_range, "effectif")
    b.field(
        "Moyens matériels",
        (
            f"{len(data.equipment)} équipement{'s' if len(data.equipment) > 1 else ''} "
            "(détail dans la liste des moyens matériels)"
            if data.equipment
            else None
        ),
        "moyens matériels (Profil > Matériel)",
    )
    if data.certifications:
        b.paragraph("Certifications et qualifications :", bold=True)
        b.bullets(
            [
                name
                + (f" n° {number}" if number else "")
                + (f", valable jusqu'au {french_date(until)}" if until else "")
                for name, number, until in data.certifications
            ]
        )
    b.field(
        "Références",
        (
            f"{len(data.references)} référence{'s' if len(data.references) > 1 else ''} "
            "(liste des références jointe)"
            if data.references
            else None
        ),
        "références de prestations similaires (Profil > Références)",
    )
    b.heading("Documents de preuve disponibles")
    if data.proofs:
        b.bullets(
            [
                PROOF_LABELS.get(kind, kind)
                + (f", valable jusqu'au {french_date(until)}" if until else "")
                for kind, until in data.proofs
            ]
        )
    else:
        b.paragraph(todo("attestations à jour (coffre-fort)"))
    b.heading("Sous-traitance")
    b.checkboxes(
        "Le candidat n'envisage pas de sous-traiter",
        "Le candidat envisage de sous-traiter (joindre un DC4 par sous-traitant)",
    )
    _signature(b, data.company)
    return b


def staff_list(data: FormData) -> DocBuilder:
    b = _builder(data, "Moyens humains", data.title.value or "")
    b.note("Personnel déclaré dans votre profil Pilao.")
    if data.staff:
        total = sum(count for _, count, _ in data.staff)
        b.table(
            ["Qualification", "Effectif", "Description"],
            [[q, str(n), d or ""] for q, n, d in data.staff] + [["**Total**", f"**{total}**", ""]],
            widths_cm=(5.5, 2.5, 8.5),
        )
    else:
        b.paragraph(todo("personnel affecté au marché (Profil > Moyens humains)"))
    b.heading("Certifications et qualifications")
    if data.certifications:
        b.table(
            ["Certification / qualification", "Numéro", "Valable jusqu'au"],
            [[n, num or "", french_date(u) or ""] for n, num, u in data.certifications],
            widths_cm=(8, 4, 4.5),
        )
    else:
        b.paragraph("Aucune certification déclarée dans votre profil.")
    return b


def equipment_list(data: FormData) -> DocBuilder:
    b = _builder(data, "Moyens matériels", data.title.value or "")
    b.note("Matériel déclaré dans votre profil Pilao.")
    if data.equipment:
        b.table(
            ["Matériel", "Catégorie", "Quantité"],
            [[n, c or "", str(q) if q is not None else ""] for n, c, q in data.equipment],
            widths_cm=(8.5, 5, 3),
        )
    else:
        b.paragraph(todo("matériel affecté au marché (Profil > Matériel)"))
    return b


def references_list(data: FormData) -> DocBuilder:
    b = _builder(data, "Liste des références", data.title.value or "")
    b.note(
        "Vos références (celles retenues pour le mémoire quand il existe), aucune n'est inventée."
    )
    if not data.references:
        b.paragraph(todo("références de prestations similaires (Profil > Références)"))
        return b
    b.table(
        ["Client", "Objet", "Lieu", "Année", "Montant HT"],
        [
            [
                f"{r.client} ({'public' if r.public else 'privé'})",
                r.title
                + (f" — {r.duration_months} mois" if r.duration_months else "")
                + (f". {r.description}" if r.description else ""),
                r.location or "",
                str(r.year) if r.year else "",
                eur(r.amount_cents) or "",
            ]
            for r in data.references
        ],
        widths_cm=(3.8, 6.7, 2.5, 1.5, 2.5),
    )
    return b


def planning(data: FormData) -> DocBuilder:
    b = _builder(data, "Trame de planning", data.title.value or "")
    b.note("Trame à adapter : seules les dates connues (DCE) sont remplies.")
    b.field(
        "Date limite de remise des offres", data.deadline.value, "date limite", data.deadline.source
    )
    b.field("Durée du marché", data.duration.value, "durée du marché", data.duration.source)
    rows = [
        [
            "Visite du site",
            data.site_visit.value or "Selon le règlement de la consultation",
            "Titulaire",
            "Prendre les mesures, repérer les contraintes d'accès et d'horaires",
        ],
        [
            "Remise de l'offre",
            data.deadline.value or todo("date limite"),
            "Titulaire",
            "Sur le profil acheteur indiqué au RC",
        ],
        ["Notification du marché", todo("date de notification"), "Acheteur", ""],
        [
            "Réunion de lancement",
            todo("date de la réunion de lancement"),
            "Acheteur et titulaire",
            "Interlocuteurs, plans, consignes de sécurité, accès",
        ],
    ]
    if CLEANING_TRADES & set(data.trades):
        rows.append(
            [
                "Reprise du personnel en place, le cas échéant",
                todo("date de reprise"),
                "Titulaire",
                "Convention collective de la propreté, annexe 7",
            ]
        )
    rows += [
        [
            "Formation des agents au site",
            todo("date de formation"),
            "Titulaire",
            "Protocoles, produits, sécurité",
        ],
        ["Démarrage des prestations", todo("date de démarrage"), "Titulaire", ""],
        [
            "Premier contrôle qualité contradictoire",
            todo("date du premier contrôle"),
            "Acheteur et titulaire",
            "",
        ],
        ["Bilans périodiques", todo("fréquence des bilans"), "Acheteur et titulaire", ""],
    ]
    b.table(
        ["Étape", "Échéance", "Responsable", "Observations"], rows, widths_cm=(4.5, 4, 3.3, 4.7)
    )
    return b


FORMS = {
    "dc1": ("DC1 — Lettre de candidature", dc1),
    "dc2": ("DC2 — Déclaration du candidat", dc2),
    "staff_list": ("Liste des moyens humains", staff_list),
    "equipment_list": ("Liste des moyens matériels", equipment_list),
    "references_list": ("Liste des références", references_list),
    "planning": ("Trame de planning", planning),
}
